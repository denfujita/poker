"""Sweep random river spots: how wrong is 'product of heads-up equities' (independent ranges)
versus the exact joint, where opponents' hidden cards must be distinct?

Also checks a closed-form exact formula (inclusion-exclusion over coinciding cards) against
brute-force enumeration. River only, so there is no runout randomness.

Run: OMP_NUM_THREADS=1 .venv/bin/python -I ../bench/blocker_sweep.py --seed 0
"""

import argparse
import itertools
import random
import statistics

import numpy as np
import eval7

DECK = [eval7.Card(r + s) for r in "23456789TJQKA" for s in "shdc"]


def reweight(w, s, f, eps=0.10, width=0.10):
    """Bet/call: keep the top f of the current weighted range (mid-rank percentile, ties as blocks)."""
    order = np.argsort(s, kind="stable")
    w_sorted, s_sorted = w[order], s[order]
    total = w.sum()
    out = np.empty_like(w)
    below, i, n = 0.0, 0, len(w)
    while i < n:
        j = i
        while j < n and s_sorted[j] == s_sorted[i]:
            j += 1
        block = w_sorted[i:j].sum()
        q = (below + block / 2) / total
        x = min(1.0, max(0.0, (q - (1 - f - width / 2)) / width))
        out[order[i:j]] = w_sorted[i:j] * (eps + (1 - eps) * x)
        below += block
        i = j
    return out


def distinct_sum(fs):
    """sum over pairwise-distinct (h_1..h_n) of prod_i fs[i][h_i], via set partitions
    (Möbius inversion on the partition lattice): coefficient prod_B (-1)^(|B|-1) (|B|-1)!."""
    n = len(fs)
    total = 0.0
    for partition in _partitions(list(range(n))):
        term = 1.0
        for block in partition:
            k = len(block)
            prod = np.ones_like(fs[0])
            for i in block:
                prod = prod * fs[i]
            term *= (-1) ** (k - 1) * _fact(k - 1) * prod.sum()
        total += term
    return total


def _fact(k):
    out = 1
    for i in range(2, k + 1):
        out *= i
    return out


def _partitions(items):
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for part in _partitions(rest):
        for i in range(len(part)):
            yield part[:i] + [[first] + part[i]] + part[i + 1:]
        yield [[first]] + part


def one_spot(rng, n_opp, f, brute):
    cards = rng.sample(DECK, 2 + 5 + n_opp)
    hero, board, shown = cards[:2], cards[2:7], cards[7:]
    seen = set(cards)
    cand = [c for c in DECK if c not in seen]
    hv = eval7.evaluate(hero + board)
    S = [np.array([eval7.evaluate([e, h] + board) for h in cand], dtype=np.int64) for e in shown]
    W = [reweight(np.ones(len(cand)), s, f) for s in S]
    beat = [np.where(hv > s, 1.0, np.where(hv == s, 0.5, 0.0)) for s in S]

    indep = 1.0
    for w, b in zip(W, beat):
        indep *= (w * b).sum() / w.sum()
    # Exact joint, ignoring split-pot interactions between opponents (ties count 0.5 each).
    exact = distinct_sum([w * b for w, b in zip(W, beat)]) / distinct_sum(W)

    if brute:
        num = den = 0.0
        for combo in itertools.product(range(len(cand)), repeat=n_opp):
            if len(set(combo)) < n_opp:
                continue
            p = 1.0
            pb = 1.0
            for i, h in enumerate(combo):
                p *= W[i][h]
                pb *= beat[i][h]
            num += p * pb
            den += p
        assert abs(num / den - exact) < 1e-9, (num / den, exact)
    return indep, exact


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--spots", type=int, default=2000)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    print(f"seed={args.seed} spots={args.spots} (river, each opponent bet/called with top f, eps=0.10)")
    for n_opp in (2, 3, 4):
        for f in (0.30, 0.15):
            diffs = []
            for k in range(args.spots):
                indep, exact = one_spot(rng, n_opp, f, brute=(k < 20 and n_opp <= 3))
                diffs.append(indep - exact)
            d = np.array(diffs)
            boot = [np.mean(rng.choices(diffs, k=len(diffs))) for _ in range(500)]
            lo, hi = np.percentile(boot, [2.5, 97.5])
            print(f"n_opp={n_opp} f={f:.2f}: independent - exact  mean {d.mean()*100:+.2f}pp "
                  f"[95% CI {lo*100:+.2f}, {hi*100:+.2f}]  |mean| {np.abs(d).mean()*100:.2f}pp  "
                  f"p99 |d| {np.percentile(np.abs(d), 99)*100:.2f}pp  max {np.abs(d).max()*100:.2f}pp")
    print("brute-force check of the closed form passed (first 20 spots, n<=3)")


if __name__ == "__main__":
    main()
