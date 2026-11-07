"""Measure what fits in the 1 ms decision budget: eval7 calls, Python MC, eval7's C MC.

Run with the kit venv, single-threaded:  OMP_NUM_THREADS=1 .venv/bin/python ../bench/bench_budget.py
"""

import random
import statistics
import time

import eval7

random.seed(0)
DECK = [eval7.Card(r + s) for r in "23456789TJQKA" for s in "shdc"]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def report(name, samples_ns, per=1):
    us = [s / 1000 / per for s in samples_ns]
    print(f"{name:55s} mean {statistics.mean(us):8.2f} us  p99 {pct(us, .99):8.2f}  max {max(us):8.2f}")


# 1. Single 7-card eval
cards = random.sample(DECK, 7)
t = []
for _ in range(20000):
    a = time.perf_counter_ns(); eval7.evaluate(cards); t.append(time.perf_counter_ns() - a)
report("eval7.evaluate 7 cards (per call)", t)

# 2. Python-loop MC: hero 2 cards vs N random 2-card opponents, flop known
def py_mc(hero, board, n_opp, iters):
    dead = set(hero) | set(board)
    deck = [c for c in DECK if c not in dead]
    need = 2 * n_opp + (5 - len(board))
    win = 0.0
    ev = eval7.evaluate
    for _ in range(iters):
        draw = random.sample(deck, need)
        runout = board + draw[: 5 - len(board)]
        h = ev(hero + runout)
        best = max(ev(draw[5 - len(board) + 2 * i: 5 - len(board) + 2 * i + 2] + runout) for i in range(n_opp))
        win += 1.0 if h > best else 0.5 if h == best else 0.0
    return win / iters

for n_opp, iters in [(1, 100), (1, 200), (3, 100)]:
    t = []
    for _ in range(300):
        cs = random.sample(DECK, 5)
        a = time.perf_counter_ns(); py_mc(cs[:2], cs[2:], n_opp, iters); t.append(time.perf_counter_ns() - a)
    report(f"python MC flop, {n_opp} opp, {iters} iters (whole call)", t)

# 3. eval7 C-level MC: hero vs a range (e.g. exposed card + any hidden card)
cs = random.sample(DECK, 6)
hero, board, exposed = cs[:2], cs[2:5], cs[5]
dead = set(cs)
rng_hands = [((exposed, c), 1.0) for c in DECK if c not in dead]
hr = eval7.HandRange("AA")
hr.hands = rng_hands  # override with the exposed-card range
for iters in [500, 2000]:
    t = []
    for _ in range(300):
        a = time.perf_counter_ns(); eval7.py_hand_vs_range_monte_carlo(hero, hr, board, iters); t.append(time.perf_counter_ns() - a)
    report(f"eval7 C MC vs exposed-card range, {iters} iters", t)
t = []
for _ in range(100):
    a = time.perf_counter_ns(); eq = eval7.py_hand_vs_range_exact(hero, hr, board + [c for c in DECK if c not in dead][:1]); t.append(time.perf_counter_ns() - a)
report("eval7 exact vs exposed-card range, turn", t)
print("sample equity", eval7.py_hand_vs_range_monte_carlo(hero, hr, board, 2000))
