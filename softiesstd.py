#!/usr/bin/python

# Implement the BitTorrent reference client as described in Chapter 5, including rarest-
# first, reciprocation and optimistic unblocking. This should be class TeamnameStd in

# teamnamestd.py. Not all the details are in Chapter 5, so you will have to make some
# assumptions. Explain all of the assumptions you make in your writeup.

import random
import logging

from messages import Upload, Request
from util import even_split
from peer import Peer

NUM_ROUNDS_CONSIDERED = 2
NUM_M_BUCKETS = 4
from collections import defaultdict

class SoftiesStd(Peer):
    def post_init(self):
        print(("post_init(): %s here!" % self.id))
        self.isLeecher = True
        self.optimisticallyUnblockedID = None

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

        # Switch to seeder if I have all the pieces (included in history)
        if np_set == set():
            logging.info(" ***** SWITCHING TO SEEDER *****")
            self.isLeecher = False

        logging.debug("%s here: still need pieces %s" % (
            self.id, needed_pieces))

        requests = []   # We'll put all the things we want here
        # Symmetry breaking is good...
        random.shuffle(needed_pieces)

        # Find the rarest pieces => piece id and count
        rarest_pieces = defaultdict(lambda: 0)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = av_set.intersection(np_set)
            for piece_id in isect:
                rarest_pieces[piece_id] += 1

        random.shuffle(peers)
        # request all available pieces from all peers!
        # (up to self.max_requests from each)
        for peer in peers:
            av_set = set(peer.available_pieces)
            isect = list(av_set.intersection(np_set))

            # Request n rarest pieces, sorted by rarity and breaking symmetry
            random.shuffle(isect)
            isect.sort(key = lambda piece_id: rarest_pieces[piece_id])
            n = min(self.max_requests, len(isect))

            for piece_id in isect[:n]:
                # aha! The peer has this piece! Request it.
                start_block = self.pieces[piece_id]
                r = Request(self.id, peer.id, piece_id, start_block)
                requests.append(r)

        logging.debug("****** +____+ requests are: %s" % requests)

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
            # LEECHER CASE
            # if self.isLeecher:
            # fewer than M buckets, so just split evenly
            if len(requests) <= NUM_M_BUCKETS:
                chosen = [request.requester_id for request in requests]
                # Evenly "split" my upload bandwidth among the one chosen requester
                bws = even_split(self.up_bw, len(chosen))

            # len(requests) > NUM_M_BUCKETS, so use optimistic + reciprocal unblocking
            else:
                # Find the number of rounds to base the history off of
                numRoundsHistory = min(
                    len(history.downloads), NUM_ROUNDS_CONSIDERED)

                # Calculate average download capacity given for previous rounds, per peer, starting from the past round
                downloadHistory = defaultdict(lambda: 0)  # key: peer_id, value: total download capacity alloted
                for i in range(1, numRoundsHistory):
                    for download in history.downloads[round-i]:
                        downloadHistory[download.from_id] += download.blocks

                # Sort requests by the top download capacity (same as average)
                requests.sort(
                    key=lambda request: downloadHistory[request.requester_id], reverse=True)

                # TAKE THE TOP M-1 DOWNLOADERS - protect for case where num requests
                selectedRequests = requests[:NUM_M_BUCKETS-1]

                # Set the chosen requests to be the top M-1 ids
                chosen = [
                    request.requester_id for request in selectedRequests]

                # bandwidth should be evenly split amongst the M-1 peers, keeping in mind the last 1/M is allocated for optimistic unblocking
                bws = even_split(self.up_bw, len(chosen)+1)

                if round % 3 != 0:
                    chosen.append(self.optimisticallyUnblockedID)
                    bws.append(self.up_bw/NUM_M_BUCKETS)

                else:
                    # Set the optimistic unblocker to be the last peer in the list
                    luckyUnblock = random.choice(requests[NUM_M_BUCKETS:])
                    self.optimisticallyUnblockedID = luckyUnblock.requester_id
                    chosen.append(self.optimisticallyUnblockedID)
                    bws.append(self.up_bw/NUM_M_BUCKETS)
            """
            # SEEDER CASE
            else:
                # fewer than M buckets, so just split evenly
                if len(requests) <= NUM_M_BUCKETS:
                    chosen = [request.requester_id for request in requests]
                    # Evenly "split" my upload bandwidth among the one chosen requester
                    bws = even_split(self.up_bw, len(chosen))
                # len(requests) > NUM_M_BUCKETS, so use optimistic + reciprocal unblocking
                else:
                    # Find the number of rounds to base the history off of
                    numRoundsHistory = min(
                        len(history.downloads), NUM_ROUNDS_CONSIDERED)

                    # Calculate average download capacity given for previous rounds, per peer, starting from the past round
                    uploadHistory = defaultdict(lambda: 0)  # key: peer_id, value: total download capacity alloted
                    for i in range(1, numRoundsHistory):
                        for upload in history.uploads[round-i]:
                            uploadHistory[upload.to_id] += upload.blocks

                    # Sort requests by the top download capacity (same as average)
                    requests.sort(
                        key=lambda request: uploadHistory[request.requester_id], reverse=True)

                    # TAKE THE TOP M-1 DOWNLOADERS - protect for case where num requests
                    selectedRequests = requests[:NUM_M_BUCKETS-1]

                    # Set the chosen requests to be the top M-1 ids
                    chosen = [
                        request.requester_id for request in selectedRequests]

                    # bandwidth should be evenly split amongst the M-1 peers, keeping in mind the last 1/M is allocated for optimistic unblocking
                    bws = even_split(self.up_bw, len(chosen)+1)

                    if round % 3 != 0:
                        chosen.append(self.optimisticallyUnblockedID)
                        bws.append(self.up_bw/NUM_M_BUCKETS)
                    else:
                        # Set the optimistic unblocker to be the last peer in the list
                        luckyUnblock = random.choice(requests[NUM_M_BUCKETS:])
                        self.optimisticallyUnblockedID = luckyUnblock.requester_id
                        chosen.append(self.optimisticallyUnblockedID)
                        bws.append(self.up_bw/NUM_M_BUCKETS)
                        """

        uploads = [Upload(self.id, peer_id, bw)
                   for (peer_id, bw) in zip(chosen, bws)]

        return uploads
