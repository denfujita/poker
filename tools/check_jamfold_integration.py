#!/usr/bin/env python3
"""Synthetic real-SDK Agent.act regressions for the restricted jam/fold adapter.

Run with the official kit virtualenv. --baseline points to frozen v4 agent.py
with its unchanged preflop_policy.json beside it. No private histories are used.
"""
import argparse
from dataclasses import replace
import importlib.util
import itertools
import json
from pathlib import Path
import random
import sys

from poker_agent_protocol.game import (
    Action, BlindLevel, Event, GameState, LegalAction, Seat, TableConfig, is_legal,
)

sys.dont_write_bytecode = True


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, Path(path).resolve())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(players=2, depth=10, kind="jam", hand=1, cards=("As", "Kd", "Qh")):
    total = depth * 20
    button = 0 if players == 2 else players - 3
    sb, bb = (0, 1) if players == 2 else (players - 2, players - 1)
    hero = sb if kind == "jam" else bb
    sb_bet = 10 if kind == "jam" else total
    seats = tuple(Seat(i, total - (sb_bet if i == sb else 20 if i == bb else 0),
                       sb_bet if i == sb else 20 if i == bb else 0,
                       "all_in" if i == sb and kind == "call" else
                       "active" if i in (sb, bb) else "folded") for i in range(players))
    history = (Event("hand", amount=hand), Event("blind", sb, 10), Event("blind", bb, 20))
    history += tuple(Event("fold", i) for i in range(players) if i not in (sb, bb))
    if kind == "call":
        history += (Event("raise", sb, total),)
    legal = (LegalAction("fold"), LegalAction("call"))
    if kind == "jam":
        legal += (LegalAction("raise", 40, total),)
    blinds = BlindLevel(10, 20)
    config = TableConfig("synthetic-jamfold", hero, players, "flop_discard_reveal", total,
                         (blinds,), 20, 250, (50, 30, 20), 1, 65536, 100)
    return GameState(history, hand, hero, cards, (), sb_bet + 20,
                     10 if kind == "jam" else total - 20, legal, history, seats,
                     button, 0, blinds, 20, players, (), config)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--baseline", required=True, type=Path)
    args = ap.parse_args()
    m = load(args.candidate, "jamfold_candidate")
    baseline = load(args.baseline, "jamfold_baseline")
    agent, old = m.Agent(), baseline.Agent()
    checks = 0

    def check(value):
        nonlocal checks
        assert value, checks
        checks += 1

    representatives = {}
    for cards, entry in m._PREFLOP_COMBOS.items():
        representatives.setdefault(entry[1], tuple(cards[i:i + 2] for i in range(0, 6, 2)))
    check(set(representatives) == set(range(40)))
    # Full bucket vectors, both action branches, every exported grid point.
    for n, depth, kind, bucket in itertools.product((2, 3, 4, 6, 8), (3, 5, 7, 10, 12, 15, 20), ("jam", "call"), range(40)):
        s = state(n, depth, kind, cards=representatives[bucket])
        spot = m.supported_jamfold_spot(s)
        check(spot is not None)
        vector = (m._PREFLOP_POLICY["jam"][str(n)]["SB"][str(depth)] if kind == "jam"
                  else m._PREFLOP_POLICY["call"][str(n)]["SB"][str(depth)]["BB"])
        check(spot[1] == vector[bucket])
        action, memory = agent.act(s, b"truncated-invalid-memory")
        check(memory == b"" and is_legal(action, s.legal_actions))
        check(action.kind in (("raise", "fold") if kind == "jam" else ("call", "fold")))

    # Known 0/1/mixed policy decisions through Agent.act. Any fallback equity
    # evaluation is a failure, especially for a defensive chart fold.
    saved_equities = m.equities
    def no_fallthrough(*args, **kwargs):
        raise AssertionError("Supported chart decision fell through to equity")
    m.equities = no_fallthrough
    fractions = {}
    for kind in ("jam", "call"):
        s = state(kind=kind)
        bucket = m._PREFLOP_COMBOS["".join(sorted(s.cards))][1]
        vector = (m._PREFLOP_POLICY["jam"]["2"]["SB"]["10"] if kind == "jam"
                  else m._PREFLOP_POLICY["call"]["2"]["SB"]["10"]["BB"])
        original = vector[bucket]
        vector[bucket] = 0
        check(agent.act(s, b"")[0].kind == "fold")
        vector[bucket] = 1
        check(agent.act(s, b"")[0].kind == ("raise" if kind == "jam" else "call"))
        vector[bucket] = .35
        decisions = []
        for hand in range(1, 2001):
            varied = replace(s, hand_number=hand)
            first = agent.act(varied, b"")[0]
            random.seed(hand)
            random.random()
            agent.act(replace(varied, hand_number=hand + 10000), b"other-table-memory")
            check(first == agent.act(varied, b"different-memory")[0])
            decisions.append(first.kind != "fold")
        fractions[kind] = sum(decisions) / len(decisions)
        check(.31 < fractions[kind] < .39)
        vector[bucket] = original
    m.equities = saved_equities

    # Unsupported states must follow the original Agent.act byte-for-byte.
    s, c = state(), state(kind="call")
    unsupported = [state(depth=9), state(players=5), state(players=7), state(players=10),
                   replace(s, blinds=BlindLevel(10, 20, 1)),
                   replace(s, blinds=BlindLevel(5, 20)),
                   replace(s, seats=(replace(s.seats[0], stack=s.seats[0].stack + 1), s.seats[1])),
                   replace(s, history=s.history + (Event("call", s.seat, 10),)),
                   replace(s, history=s.history + (Event("check", s.seat),)),
                   replace(s, history=s.history + (Event("ante", s.seat, 1),)),
                   replace(s, history=s.history[1:2]),
                   replace(s, pot=s.pot + 1), replace(s, to_call=s.to_call + 1),
                   replace(c, history=c.history + (Event("raise", c.seat, 400),)),
                   replace(c, seats=(replace(c.seats[0], status="active"), c.seats[1])),
                   replace(c, pot=c.pot + 1), replace(c, to_call=c.to_call + 1)]
    multi = state(players=8)
    unsupported.append(replace(multi, seats=(replace(multi.seats[0], status="active"),) + multi.seats[1:]))
    unsupported.append(replace(multi, history=multi.history[:-1]))
    unsupported.append(replace(multi, seat=0, cards=("2c", "3d", "7h")))
    for item in unsupported:
        check(m.supported_jamfold_spot(item) is None)
        check(agent.act(item, b"invalid") == old.act(item, b"invalid"))

    # Folded stacks do not enter a two-player chip-EV pot; physical seat holes
    # and blind-event order must not change which player is the SB/button.
    folded_diff = replace(multi, seats=(replace(multi.seats[0], stack=1234),) + multi.seats[1:])
    check(m.supported_jamfold_spot(folded_diff) is not None)
    reordered = replace(s, history=(s.history[0], s.history[2], s.history[1]))
    check(agent.act(s, b"") == agent.act(reordered, b""))
    for cards in itertools.permutations(s.cards):
        check(agent.act(s, b"") == agent.act(replace(s, cards=cards), b""))

    print(json.dumps({"checks": checks, "failed": 0, "mixture_frequency": fractions,
                      "outside_domain_states_equal_to_v4": len(unsupported)}, indent=2))


if __name__ == "__main__":
    main()
