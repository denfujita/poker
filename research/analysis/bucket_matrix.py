"""Bucket-vs-bucket heads-up showdown equity for 3-card hands (Bay Area variant).

Buckets: hand classes sorted by true heads-up equity (preflop_equity.csv, eq3_vs1), cut into K
groups of equal combo mass. E[i, j] = P(random hand from bucket i beats random hand from bucket j),
both keeping the best made pair on the flop (same selection model as preflop_equity.py),
with card removal (hands sampled without overlap). Ties count 1/2.

Usage: python analysis/bucket_matrix.py --k 40 --trials 3000
Outputs data/derived/buckets_k<K>.csv (class -> bucket) and data/derived/bucket_equity_k<K>.npy
"""

import argparse
import itertools
import multiprocessing as mp
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preflop_equity import CARD, DECK, EV, canonical, keep, label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def assign_buckets(k):
    d = pd.read_csv(ROOT / "data/derived/preflop_equity.csv")
    combos = {}
    by_class = {}
    for c in itertools.combinations(DECK, 3):
        lab = label(canonical(c))
        by_class.setdefault(lab, []).append(c)
    d["combos"] = d["class"].map(lambda x: len(by_class[x]))
    d = d.sort_values("eq3_vs1", ascending=False).reset_index(drop=True)
    cum = d.combos.cumsum() / d.combos.sum()
    # bucket 0 = strongest; class goes to the bucket its combo-mass midpoint falls in
    mid = cum - d.combos / d.combos.sum() / 2
    d["bucket"] = np.minimum((mid * k).astype(int), k - 1)
    d["pct_mid"] = mid
    return d, by_class


def cell(args):
    i, j, hands_i, hands_j, trials, seed = args
    rng = random.Random(seed)
    won = 0.0
    n = 0
    while n < trials:
        a = rng.choice(hands_i)
        b = rng.choice(hands_j)
        if set(a) & set(b):
            continue
        dead = set(a) | set(b)
        deck = [CARD[c] for c in DECK if c not in dead]
        board = rng.sample(deck, 5)
        flop = board[:3]
        av = EV(list(keep([CARD[c] for c in a], flop)) + board)
        bv = EV(list(keep([CARD[c] for c in b], flop)) + board)
        won += 1.0 if av > bv else 0.5 if av == bv else 0.0
        n += 1
    return i, j, won / trials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=40)
    ap.add_argument("--trials", type=int, default=3000)
    args = ap.parse_args()
    d, by_class = assign_buckets(args.k)
    hands = [[h for cls in d[d.bucket == b]["class"] for h in by_class[cls]] for b in range(args.k)]
    d.to_csv(ROOT / f"data/derived/buckets_k{args.k}.csv", index=False)
    jobs = [(i, j, hands[i], hands[j], args.trials, 1_000_003 * i + j) for i in range(args.k) for j in range(i, args.k)]
    t = time.time()
    E = np.full((args.k, args.k), np.nan)
    with mp.Pool() as pool:
        for i, j, e in pool.imap_unordered(cell, jobs, chunksize=4):
            if i == j:
                E[i, i] = 0.5  # same bucket: exactly 1/2 by symmetry (MC value would only add noise)
            else:
                E[i, j] = e
                E[j, i] = 1 - e
    np.save(ROOT / f"data/derived/bucket_equity_k{args.k}.npy", E)
    print(f"k={args.k} trials={args.trials} cells={len(jobs)} in {time.time() - t:.0f}s; "
          f"E[0,-1]={E[0, -1]:.3f} E[mid,mid]={E[args.k // 2, args.k // 2]:.3f}")


if __name__ == "__main__":
    main()
