#!/usr/bin/python

# Implement the PropShare client. This should be class TeamnamePropShare in teamnamepropshare.py.
# The PropShare client allocates upload bandwidth based on the downloads received from
# peers in the previous round: It calculates what share each peer contributed to the total
# download and allocates its own bandwidth proportionally. In addition it reserves a small
# share of its bandwidth for optimistic unblocking (e.g., 10%). For example
# • In round k the client received 4, 6, 1, 9 blocks from peers A, B, C, D, respectively
# • In round k + 1 peers A, B, E, F request pieces from the client
# • The client allocates 4

# (4+6)/6 · 90% = 36%

# (4+6)/6 · 90% = 54% of its upload bandwidth

# to A and B, respectively
# • E is randomly selected and allocated 10%

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

from collections import defaultdict

# PERCENT OF UPLOAD BANDWIDTH TO ALLOCATE TO OPTIMISTIC UNBLOCKING
OPTIMISTIC_PERCENTAGE = 0.25

class SoftiesPropShare(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))

    def requests(self, peers, history):
        """
        peers: available info about the peers (who has what pieces)
        history: what's happened so far as far as this peer can see

        returns: a list of Request() objects

        This will be called after update_pieces() with the most recent state.
        """
        def needed(i): return self.pieces[i] < self.conf.blocks_per_piece
        needed_pieces = list(filter(needed, list(range(len(self.pieces)))))
        np_set = set(needed_pieces)  # sets support fast intersection ops.

        logging.debug("%s here: still need pieces %s" % (self.id, needed_pieces))

        # Calculate rarity of pieces from peers
        rarity = defaultdict(lambda: 0)
        for p in peers:
            for piece_id in p.available_pieces:
                rarity[piece_id] += 1

        requests = []   # We'll put all the things we want here

        # Symmetry breaking is good...
        random.shuffle(needed_pieces)
        random.shuffle(peers)

        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = list(av_set.intersection(np_set))

            # Request n rarest pieces, sorted by rarity and breaking symmetry
            random.shuffle(isect)
            isect.sort(key = lambda x: rarity[x])
            n = min(self.max_requests, len(isect))
        
            for piece_id in isect[:n]:
                # aha! The peer has this piece! Request it.
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

        return requests

    def uploads(self, requests, peers, history):
        """
        requests -- a list of the requests for this peer for this round
        peers -- available info about all the peers
        history -- history for all previous rounds

        returns: list of Upload objects.

        In each round, this will be called after requests().
        """

        round = history.current_round()
        logging.debug("%s again.  It's round %d." % (
            self.id, round))

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
        else:
            logging.debug("Still here: uploading based on PropShare")

            # First Round (Round 0) is a special case
            if round == 0:
                # use optimistic percentage and pick a request at random, else do nothing
                peer = random.choice(peers)
                chosen = [peer.id]
                bws = [self.up_bw]
                logging.debug("Shooting my shot because it's R0!")
            # For Round 1+
            else:
                # grab history of downloads
                last_downloads = history.downloads[round - 1]

                # get total number of blocks downloaded from each peer in the previous round
                downloadedFrom = defaultdict(lambda: 0)
                for d in last_downloads:
                    downloadedFrom[d.from_id] += d.blocks

                bandwidthToAllocate = self.up_bw * (1-OPTIMISTIC_PERCENTAGE)

                # determine which requesting peers we downloaded from last round
                downloadedFromAndRequested = defaultdict(lambda: 0)
                newRequests = []
                for r in requests:
                    if r.requester_id in downloadedFrom:
                        downloadedFromAndRequested[r.requester_id] = downloadedFrom[r.requester_id]
                    else:
                        newRequests.append(r)

                # allocate bandwidth proportionally to requesting peers we downloaded from last round
                totalShare = sum(downloadedFromAndRequested.values())
                chosen = [k for k in downloadedFromAndRequested.keys()]
                bws = [
                    v/totalShare*bandwidthToAllocate for v in downloadedFromAndRequested.values()]
                
                # Last optimistic unblocking
                if len(newRequests) != 0:
                    request = random.choice(newRequests)
                    chosen.append(request.requester_id)
                    bws.append(self.up_bw - sum(bws))
                logging.debug(
                    "******* Fulfilling requests for these peers: %s in the quantity of %s" % (str(
                        chosen), str(bws)))

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads
