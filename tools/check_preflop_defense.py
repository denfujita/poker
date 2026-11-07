#!/usr/bin/env python3
"""Generated real-engine regression for the isolated affordable 3-bet defense.

Use the official kit environment. No private histories are loaded or printed.
"""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from poker_agent_protocol.game import Action, BlindLevel, Event, is_legal
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant

sys.dont_write_bytecode = True


def load(path, name):
    path = path.resolve()
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.path.pop(0)
    return module


def engine_state(seed, players=8, stack=2000, opening=50, reraise=160, ante=0):
    table = SitAndGo(
        rules=TableRules(variant="flop_discard_reveal", players=players,
                         starting_stack=stack, blinds=(BlindLevel(10, 20, ante),), hand_cap=1),
        variant=load_variant("flop_discard_reveal"), table_id=seed, seed=seed)
    initial = table.decision()
    hero = initial.seat
    bb = next(e.seat for e in initial.history if e.kind == "blind" and e.amount == 20)
    assert table.apply(Action.raise_to(opening))
    current = table.decision()
    while current.seat != bb:
        assert current.seat != hero
        assert table.apply(Action.fold())
        current = table.decision()
    assert table.apply(Action.raise_to(reraise))
    current = table.decision()
    assert current.seat == hero
    return current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", type=Path)
    ap.add_argument("candidate", type=Path)
    args = ap.parse_args()
    base, bot = load(args.baseline, "base_defense"), load(args.candidate, "candidate_defense")
    check_count = 0

    def check(value):
        nonlocal check_count
        assert value, check_count
        check_count += 1

    state = engine_state("defense-positive")
    check(bot.affordable_heads_up_threebet(state, bot.preflop_context(state)))
    for equity in (.1, .4, .7, .99):
        for percentile in (.02, .04, .0414, .06, .08, .081, .12):
            old = base.preflop_action(state, percentile, equity, state.pot + state.to_call)
            new = bot.preflop_action(state, percentile, equity, state.pot + state.to_call)
            check(is_legal(new, state.legal_actions))
            if .04 < percentile <= .08 and equity >= state.to_call / (state.pot + state.to_call) + .10:
                check(old.kind == "fold" and new.kind == "call")
            else:
                check(old == new)
    check(base.preflop_action(state, .06) == Action.fold())
    check(bot.preflop_action(state, .06) is None)
    # Non-chip acknowledgements cannot make a supported response unreachable.
    extra = replace(state, history=state.history + (Event("prize_the_shover", state.seat),))
    check(bot.affordable_heads_up_threebet(extra, bot.preflop_context(extra)))

    negatives = [
        engine_state("defense-shallow", stack=800),
        engine_state("defense-large-open", opening=80),
        engine_state("defense-large-reraise", reraise=300),
        engine_state("defense-all-in", reraise=2000),
        engine_state("defense-six-handed", players=6),
        engine_state("defense-ante", ante=2),
        replace(state, history=state.history + (Event("call", state.seat, 0),)),
    ]
    for excluded in negatives:
        check(not bot.affordable_heads_up_threebet(excluded, bot.preflop_context(excluded)))
        for equity in (.1, .6, .99):
            check(base.preflop_action(excluded, .06, equity, excluded.pot + excluded.to_call)
                  == bot.preflop_action(excluded, .06, equity, excluded.pot + excluded.to_call))
        check(base.Agent().act(excluded, b"bad-memory") == bot.Agent().act(excluded, b"bad-memory"))
    all_in = negatives[3]
    check(any(e.kind == "prize_the_shover" for e in all_in.history))

    changed = 0
    sampled = 0
    for seed in range(160):
        current = engine_state("defense-replay-" + str(seed))
        old, _ = base.Agent().act(current, b"")
        new, memory = bot.Agent().act(current, b"truncated")
        check(is_legal(new, current.legal_actions) and memory == b"")
        if old != new:
            percentile = bot._PREFLOP_COMBOS["".join(sorted(current.cards))][0]
            check(.04 < percentile <= .08 and old.kind == "fold" and new.kind == "call")
            changed += 1
        sampled += 1
    check(changed > 0)
    print(json.dumps({"assertions": check_count, "real_engine_states": sampled + len(negatives) + 1,
                      "normal_entry_changes": changed, "failed": 0,
                      "baseline_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
                      "candidate_sha256": hashlib.sha256(args.candidate.read_bytes()).hexdigest()}, indent=2))


if __name__ == "__main__":
    main()
