#!/usr/bin/python

# This is a dummy peer that just illustrates the available information your peers
# have available.

# You'll want to copy this file to AgentNameXXX.py for various versions of XXX,
# probably get rid of the silly logging messages, and then add more logic.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer
from collections import defaultdict

class SoftiesTourney(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.d = defaultdict(lambda: self.up_bw / 4)
        self.u = defaultdict(lambda: self.up_bw / 4)
        self.alpha = 0.11
        self.gamma = 0.07
        self.r = 3

        self.optimistic = 0.26 * self.up_bw
        self.optimistic_id = None

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
            logging.debug("I have requests!")
            peer_requesters = [request.requester_id for request in requests]

            chosen = []
            bws = []
            bw_left = self.up_bw

            # Oportunistic unblocking every other round
            if round % 2 == 0:
                # Choose a random peer to unblock
                self.optimistic_id = random.choice(peer_requesters)
                chosen = [self.optimistic_id]
                peer_requesters.remove(self.optimistic_id)
            # During unblocking rounds
            elif self.optimistic_id:
                # If the peer is still requesting, unblock it
                if self.optimistic_id in peer_requesters:
                    chosen = [self.optimistic_id]
                    peer_requesters.remove(self.optimistic_id)
                # Otherwise, choose a new peer to unblock in the meantime
                else:
                    chosen = [random.choice(peer_requesters)]
                    peer_requesters.remove(chosen[0])
            bws = [self.optimistic]
            bw_left -= self.optimistic

            if round > 0:    
                # Update download estimates
                total_downloaded = defaultdict(lambda: 0)
                downloaded_from = set()
                for d in history.downloads[history.last_round()]:
                    total_downloaded[d.from_id] += d.blocks
                    downloaded_from.add(d.from_id)
                for p, t_d in total_downloaded.items():
                    self.d[p] = t_d

                # Update upload estimates
                uploaded_to = set()
                for u in history.uploads[history.last_round()]:
                    uploaded_to.add(u.to_id)

                for p in uploaded_to:
                    # If we uploaded to a peer that didn't let us download, increase upload estimate
                    if p not in downloaded_from:
                        self.u[p] *= 1 + self.alpha

                    # If we uploaded to a peer that let us download, decrease upload estimate after r rounds
                    elif history.current_round() >= self.r:
                        present = False
                        for d in history.downloads[round - self.r: round]:
                            present = False
                            for dd in d:
                                # Was this peer one of the ones we downloaded from?
                                if dd.from_id == p:
                                    present = True
                                    break
                            # We didn't download from this peer r rounds in a row
                            if not present:
                                break
                        if present:
                            self.u[p] *= 1 - self.gamma 

            # Order peers by download/upload ratio
            peer_requesters = sorted(peer_requesters, key=lambda p: self.d[p] / self.u[p], reverse=True)

            # Upload to peers in order of download/upload ratio until we run out of bandwidth
            for p in peer_requesters:
                bw_left -= self.u[p]
                if bw_left < 0:
                    break
                chosen.append(p)
                bws.append(self.u[p])

        # create actual uploads out of the list of peer ids and bandwidths
        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads
