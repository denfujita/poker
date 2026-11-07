"""Synthetic exact heads-up river regressions; no private hand histories.

Run in the official kit environment, optionally passing --baseline OLD_AGENT
to reproduce old sampling error and verify exact equality outside this scope.
"""
import argparse
import hashlib
import importlib.util
import math
import random
from pathlib import Path

import eval7


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def enumerate_hidden(bot, cards, board, exposed, discarded, public, ranges):
    blocked = set(cards + board + exposed + discarded + public)
    choices = [text for text in bot._TEXT if text not in blocked]
    mine = eval7.evaluate([eval7.Card(c) for c in cards + board])
    hands = [tuple(eval7.Card(c) for c in exposed + (hidden,)) for hidden in choices]
    weights = [bot._range_weight(hand, ranges[0]) if ranges else 1.0 for hand in hands]
    values = [eval7.evaluate(tuple(eval7.Card(c) for c in board) + hand) for hand in hands]
    win = math.fsum(w for w, score in zip(weights, values) if mine > score)
    tie = math.fsum(w for w, score in zip(weights, values) if mine == score)
    return (win + .5 * tie) / math.fsum(weights)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    bot = load(args.candidate, "heads_up_candidate")
    baseline = load(args.baseline, "heads_up_baseline") if args.baseline else None
    checks = old_errors = 0
    max_error = 0.0
    rng = random.Random(821412)

    def verify(cards, board, exposed, discarded=(), public=(), weighted=False):
        nonlocal checks, old_errors, max_error
        ranges = ()
        if weighted:
            flop = tuple(bot._CARD[c] for c in board[:3])
            turn = tuple(bot._CARD[c] for c in board[:4])
            ranges = (((3.75, flop), (4.5, turn)),)
        expected = enumerate_hidden(bot, cards, board, exposed, discarded, public, ranges)
        params = (cards, board, 1, discarded, (exposed,), public, ranges)
        result = bot.equities(*params)
        error = abs(result[0] - expected)
        max_error = max(max_error, error)
        assert len(result) == 1 and error < 1e-12, (result, expected, params)
        groups = bot.equities(*params, contender_groups=((0,), (), (0,)))
        assert groups == (result, (1.0,), result)
        # Including already-blocked exposed/own cards again must not alter the deck.
        duplicate_public = public + exposed + cards
        assert bot.equities(cards, board, 1, discarded, (exposed,), duplicate_public, ranges) == result
        checks += 3
        if baseline and abs(baseline.equities(*params)[0] - expected) > 1e-8:
            old_errors += 1

    # Board ties, unique public quads, hidden flush completions and kickers.
    cases = (
        (("2c", "2d"), ("As", "Ks", "Qs", "Js", "Ts"), ("3c",), (), ()),
        (("Kh", "Kd"), ("As", "Ah", "Ac", "7d", "2h"), ("Ad",), ("Qs",), ("Jc",)),
        (("Qc", "Qd"), ("As", "Ks", "8s", "3s", "2h"), ("Jh",), ("Ts",), ("Qs",)),
        (("Ac", "8c"), ("Kh", "Kd", "7s", "7d", "2s"), ("Ah",), ("9c",), ("3h",)),
    )
    for case in cases:
        verify(*case)
        verify(*case, weighted=True)
    for i in range(50):
        dealt = rng.sample(bot._TEXT, 12)
        verify(tuple(dealt[:2]), tuple(dealt[2:7]), (dealt[7],),
               (dealt[8],), tuple(dealt[9:]), weighted=bool(i % 2))

    if baseline:
        assert old_errors > 0, "synthetic cases should reproduce old sampling error"
        checks += 1
        # All excluded domains must follow the byte-identical original sampler.
        domains = ((2, 3, 1, 1), (2, 4, 1, 1), (2, 5, 1, 0),
                   (2, 5, 1, 2), (2, 5, 2, 1), (2, 5, 3, 1),
                   (3, 0, 3, 0), (3, 3, 2, 0))
        for n_hole, n_board, opponents, n_shown in domains:
            for _ in range(10):
                dealt = rng.sample(bot._TEXT, 22)
                cards = tuple(dealt[:n_hole]); board = tuple(dealt[n_hole:n_hole + n_board])
                start = n_hole + n_board
                exposed = tuple(tuple(dealt[start + j * n_shown:start + (j + 1) * n_shown])
                                for j in range(opponents))
                params = (cards, board, opponents, (), exposed)
                assert bot.equities(*params) == baseline.equities(*params), params
                full = (tuple(range(opponents)),)
                assert bot.equities(*params, contender_groups=full) == baseline.equities(*params, contender_groups=full)
                checks += 2
    print({"source_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
           "passed": checks, "failed": 0, "synthetic_exact_cases": 58,
           "baseline_sampling_errors_reproduced": old_errors,
           "maximum_absolute_error": max_error})


if __name__ == "__main__":
    main()
