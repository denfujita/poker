"""Compare exact river side-pot integration with an ordered-pair oracle.

All cases are synthetic. Run using the official starter kit's Python environment.
The oracle enumerates every distinct pair of hidden cards, without using the
candidate's bucket products or collision-subtraction calculation.
"""
import argparse
import hashlib
import importlib.util
import random
from pathlib import Path


GROUPS = ((0, 1), (0,), (1,), ())


def oracle(bot, cards, board, exposed, discarded=(), dead_public=(), ranges=()):
    known = set(cards + board + discarded + dead_public + sum(exposed, ()))
    available = [card for card in bot._TEXT if card not in known]
    community = tuple(bot._CARD[card] for card in board)
    hero = bot._EVALUATE(community + tuple(bot._CARD[card] for card in cards))
    opponents = []
    for i, shown in enumerate(exposed):
        fixed = tuple(bot._CARD[card] for card in shown)
        rows = []
        for card in available:
            hand = fixed + (bot._CARD[card],)
            rows.append((bot._EVALUATE(community + hand),
                         bot._range_weight(hand, ranges[i]) if ranges else 1.0))
        opponents.append(rows)
    total_weight = 0.0
    totals = [0.0] * len(GROUPS)
    for i, (first_score, first_weight) in enumerate(opponents[0]):
        for j, (second_score, second_weight) in enumerate(opponents[1]):
            if i == j:
                continue
            weight = first_weight * second_weight
            scores = (first_score, second_score)
            total_weight += weight
            for k, group in enumerate(GROUPS):
                relevant = [scores[index] for index in group]
                best = max(relevant, default=-1)
                if hero > best:
                    totals[k] += weight
                elif hero == best:
                    totals[k] += weight / (1 + relevant.count(best))
    return tuple(value / total_weight for value in totals)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("exact_river_candidate", args.candidate)
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    checks = 0
    max_error = 0.0

    def verify(cards, board, exposed, discarded=(), dead_public=(), weighted=False):
        nonlocal checks, max_error
        ranges = ()
        if weighted:
            flop = tuple(bot._CARD[card] for card in board[:3])
            turn = tuple(bot._CARD[card] for card in board[:4])
            ranges = (((2.75, flop), (4.25, turn)), ((.5, ()), (3.5, flop)))
        expected = oracle(bot, cards, board, exposed, discarded, dead_public, ranges)
        actual = tuple(value[0] for value in bot.equities(
            cards, board, 2, discarded, exposed, dead_public, ranges,
            contender_groups=GROUPS))
        error = max(abs(a - e) for a, e in zip(actual, expected))
        max_error = max(max_error, error)
        assert error < 1e-11, (cards, board, exposed, actual, expected)
        assert actual[3] == 1.0
        checks += len(GROUPS)
        # Ordinary single-pot mode retains precisely the same sampled path.
        common = (cards, board, 2, discarded, exposed, dead_public, ranges)
        assert bot.equities(*common, contender_groups=((0, 1),)) == (bot.equities(*common),)
        checks += 1

    # Guaranteed side win/main loss, all-board ties, partial kickers/ties, and
    # opponents with a possible straight/flush versus a private made hand.
    cases = (
        (("Kh", "Kd"), ("As", "Ah", "Ac", "7d", "2h"), (("Ad",), ("3c",)), ("Qs",), ("Jc",)),
        (("2c", "2d"), ("As", "Ks", "Qs", "Js", "Ts"), (("3c",), ("4c",)), (), ()),
        (("Ac", "8c"), ("Kh", "Kd", "7s", "7d", "2s"), (("Ah",), ("3c",)), ("9c",), ()),
        (("9c", "9d"), ("Kh", "8h", "7h", "2h", "9s"), (("Ah",), ("6h",)), (), ("Th",)),
        (("Qc", "Jd"), ("Ts", "9h", "8d", "3s", "2h"), (("Qs",), ("Th",)), ("Ad",), ("7c",)),
    )
    for case in cases:
        verify(*case)
        verify(*case, weighted=True)
    rng = random.Random(19427)
    for i in range(20):
        dealt = rng.sample(bot._TEXT, 12)
        verify(tuple(dealt[:2]), tuple(dealt[2:7]), ((dealt[7],), (dealt[8],)),
               (dealt[9],), tuple(dealt[10:]), weighted=bool(i % 2))
    print({"source_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest(),
           "passed": checks, "failed": 0, "joint_cases": 30, "max_absolute_error": max_error})


if __name__ == "__main__":
    main()
