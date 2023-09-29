#!/usr/bin/python

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer
from collections import defaultdict


class SoftiesTyrant(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.d = defaultdict(lambda: self.up_bw / 4)
        self.u = defaultdict(lambda: self.up_bw / 4)
        self.alpha = 0.11
        self.gamma = 0.07
        self.r = 3

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

        # logging.debug("%s here: still need pieces %s" % (self.id, needed_pieces))

        # logging.debug("%s still here. Here are some peers:" % self.id)
        rarity = defaultdict(lambda: 0)
        for p in peers:
            logging.debug("id: %s, available pieces: %s" %
                          (p.id, p.available_pieces))
            for piece_id in p.available_pieces:
                rarity[piece_id] += 1
        """
        logging.debug("And look, I have my entire history available too:")
        logging.debug(
            "look at the AgentHistory class in history.py for details")
        logging.debug(str(history))
        """

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)

        # Sort peers by id.  This is probably not a useful sort, but other
        # sorts might be useful
        random.shuffle(peers)
        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = list(av_set.intersection(np_set))
            isect.sort(key = lambda x: rarity[x])
            n = min(self.max_requests, len(isect))
            # More symmetry breaking -- ask for random pieces.
            # This would be the place to try fancier piece-requesting strategies
            # to avoid getting the same thing from multiple peers at a time.

            for piece_id in isect[:n]:
                # aha! The peer has this piece! Request it.
                # which part of the piece do we need next?
                # (must get the next-needed blocks in order)
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
        # One could look at other stuff in the history too here.
        # For example, history.downloads[round-1] (if round != 0, of course)
        # has a list of Download objects for each Download to this peer in
        # the previous round.

        if len(requests) == 0:
            logging.debug("No one wants my pieces!")
            chosen = []
            bws = []
        else:
            logging.debug("I have requests!")
            peer_requesters = [request.requester_id for request in requests]

            if round > 0:    
                total_downloaded = defaultdict(lambda: 0)
                downloaded_from = set()
                for d in history.downloads[history.last_round()]:
                    total_downloaded[d.from_id] += d.blocks
                    downloaded_from.add(d.from_id)

                for p, t_d in total_downloaded.items():
                    self.d[p] = t_d
        
                uploaded_to = set()
                for u in history.uploads[history.last_round()]:
                    uploaded_to.add(u.to_id)

                for p in uploaded_to:
                    if p not in downloaded_from:
                        self.u[p] *= 1 + self.alpha
                    elif history.current_round() >= self.r:
                        present = False
                        for d in history.downloads[round - self.r: round]:
                            present = False
                            for dd in d:
                                if dd.from_id == p:
                                    present = True
                                    break
                            if not present:
                                break
                        if present:
                            self.u[p] *= 1 - self.gamma 

            peer_requesters = sorted(peer_requesters, key=lambda p: self.d[p] / self.u[p], reverse=True)

            chosen = []
            bws = []
            bw_left = self.up_bw
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
