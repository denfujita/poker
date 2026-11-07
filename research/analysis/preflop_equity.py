"""Preflop equity of every 3-card hand class in the Bay Area variant, vs. best-2-card hold'em equity.

Model (stated assumptions):
- All players hold 3 random cards; every player keeps the pair maximizing eval7.evaluate(pair + flop)
  (made hand on the flop, draws ignored), then turn and river are dealt. No folding: pure showdown equity.
- "best2" = max over the 3 two-card subsets of plain hold'em equity vs ONE random 2-card hand.
Monte Carlo per class; seeds fixed per class, so reruns are identical.

Usage: python analysis/preflop_equity.py --trials 2000 --opps 1 3 --out data/derived/preflop_equity.csv
"""

import argparse
import csv
import itertools
import multiprocessing as mp
import random
import subprocess
import time
from pathlib import Path

import eval7

RANKS = "23456789TJQKA"
SUITS = "shdc"
DECK = [r + s for r in RANKS for s in SUITS]
CARD = {c: eval7.Card(c) for c in DECK}
EV = eval7.evaluate


def canonical(cards):
    """Suit-isomorphism class key: min over suit relabelings of the sorted card tuple."""
    best = None
    for perm in itertools.permutations(SUITS):
        m = {s: SUITS.index(p) for s, p in zip(SUITS, perm)}  # ints, so hash(key) is stable across processes
        key = tuple(sorted((RANKS.index(c[0]), m[c[1]]) for c in cards))
        if best is None or key < best:
            best = key
    return best


def label(key):
    """Unique class label: ranks high to low, suits as canonical letters, e.g. 'AaKaQb' (AK suited + Q)."""
    return "".join(RANKS[r] + "abcd"[s] for r, s in sorted(key, key=lambda k: (-k[0], k[1])))


def keep(hand3, flop):
    return max(itertools.combinations(hand3, 2), key=lambda p: EV(list(p) + flop))


def equity3(hero, n_opp, trials, rng):
    dead = set(hero)
    deck = [CARD[c] for c in DECK if c not in dead]
    hero_c = [CARD[c] for c in hero]
    won = 0.0
    for _ in range(trials):
        draw = rng.sample(deck, 5 + 3 * n_opp)
        board = draw[:5]
        flop = board[:3]
        hv = EV(list(keep(hero_c, flop)) + board)
        best, ties = -1, 0
        for i in range(n_opp):
            ov = EV(list(keep(draw[5 + 3 * i: 8 + 3 * i], flop)) + board)
            if ov > best:
                best, ties = ov, 1
            elif ov == best:
                ties += 1
        if hv > best:
            won += 1
        elif hv == best:
            won += 1 / (ties + 1)
    return won / trials


def equity2(pair, trials, rng):
    dead = set(pair)
    deck = [CARD[c] for c in DECK if c not in dead]
    pc = [CARD[c] for c in pair]
    won = 0.0
    for _ in range(trials):
        d = rng.sample(deck, 7)
        board = d[:5]
        a, b = EV(pc + board), EV(d[5:7] + board)
        won += 1.0 if a > b else 0.5 if a == b else 0.0
    return won / trials


def job(args):
    key, rep, trials, opps = args
    rng = random.Random(hash(key) & 0xFFFFFFFF)  # deterministic per class (hash of int tuple is stable)
    row = {"class": label(key), "example": "".join(rep)}
    for n in opps:
        row[f"eq3_vs{n}"] = equity3(rep, n, trials, rng)
    row["best2_holdem"] = max(equity2(p, trials, rng) for p in itertools.combinations(rep, 2))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--opps", type=int, nargs="+", default=[1, 3])
    ap.add_argument("--out", type=Path, default=Path("data/derived/preflop_equity.csv"))
    args = ap.parse_args()
    classes = {}
    for combo in itertools.combinations(DECK, 3):
        classes.setdefault(canonical(combo), combo)
    print(f"classes={len(classes)} trials={args.trials} opps={args.opps}", flush=True)
    t = time.time()
    with mp.Pool() as pool:
        rows = pool.map(job, [(k, v, args.trials, args.opps) for k, v in classes.items()], chunksize=8)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "no-git"
    print(f"wrote {args.out} in {time.time() - t:.0f}s (code {sha})")


if __name__ == "__main__":
    main()
