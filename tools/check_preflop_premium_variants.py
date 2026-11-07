#!/usr/bin/env python3
"""Generated-engine checks for separate premium sampling / value-3-bet trials."""
import argparse
import ast
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from poker_agent_protocol.game import Action, BlindLevel, is_legal
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant

sys.dont_write_bytecode = True


def load(path, name):
    sys.path.insert(0, str(path.resolve().parent))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.path.pop(0)
    return mod


def state(seed, bb_hero=False, stack=2000, opening=50, players=8, ante=0, limp=False):
    table = SitAndGo(rules=TableRules(variant="flop_discard_reveal", players=players,
                                     starting_stack=stack, blinds=(BlindLevel(10, 20, ante),), hand_cap=1),
                     variant=load_variant("flop_discard_reveal"), table_id=seed, seed=seed)
    initial = table.decision()
    bb = next(e.seat for e in initial.history if e.kind == "blind" and e.amount == 20)
    if limp:
        assert table.apply(Action.call())
        table.decision()
    assert table.apply(Action.raise_to(opening))
    current = table.decision()
    if bb_hero:
        while current.seat != bb:
            assert table.apply(Action.fold())
            current = table.decision()
    return current


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("baseline", type=Path)
    ap.add_argument("sampling", type=Path)
    ap.add_argument("threebet", type=Path)
    args = ap.parse_args()
    base = load(args.baseline, "premium_base")
    sample = load(args.sampling, "premium_sampling")
    bet = load(args.threebet, "premium_threebet")
    checks = 0
    def check(value):
        nonlocal checks
        assert value, checks
        checks += 1
    def functions(path):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef)}
    old = functions(args.baseline)
    for path, permitted in ((args.sampling, {"equities", "decide_v7"}),
                            (args.threebet, {"preflop_action"})):
        new = functions(path)
        check({name for name in old if new.get(name) != old[name]} == permitted)

    premium = ("As", "Ah", "Kd")
    weak = ("2s", "4h", "7d")
    for bb_hero in (False, True):
        generated = state("premium-route-" + str(bb_hero), bb_hero=bb_hero)
        current = replace(generated, cards=premium)
        percentile = sample._PREFLOP_COMBOS["".join(sorted(current.cards))][0]
        check(sample.premium_small_open(current, sample.preflop_context(current), percentile))
        observed = []
        original = sample.equities
        def capture(*a, **kw):
            observed.append(kw.get("sample_count"))
            return original(*a, **kw)
        sample.equities = capture
        actual, memory = sample.Agent().act(current, b"truncated")
        sample.equities = original
        check(observed == [64] and is_legal(actual, current.legal_actions) and memory == b"")
        original = bet.equities
        def fail(*a, **kw):
            raise AssertionError("Premium value proposal fell through to showdown sampling")
        bet.equities = fail
        actual, memory = bet.Agent().act(current, b"truncated")
        bet.equities = original
        check(actual == Action.raise_to(200 if bb_hero else 150))
        check(is_legal(actual, current.legal_actions) and memory == b"")
        hero = next(s for s in current.seats if s.seat == current.seat)
        check(actual.amount < hero.stack + hero.bet)
        weak_state = replace(current, cards=weak)
        check(sample.Agent().act(weak_state, b"") == base.Agent().act(weak_state, b""))
        check(bet.Agent().act(weak_state, b"") == base.Agent().act(weak_state, b""))

    excluded = [state("premium-short", stack=800), state("premium-large", opening=100),
                state("premium-all-in", opening=2000), state("premium-six", players=6),
                state("premium-ante", ante=2), state("premium-limp", limp=True)]
    for item in excluded:
        current = replace(item, cards=premium)
        percentile = sample._PREFLOP_COMBOS["".join(sorted(current.cards))][0]
        check(not sample.premium_small_open(current, sample.preflop_context(current), percentile))
        check(sample.Agent().act(current, b"") == base.Agent().act(current, b""))
        check(bet.Agent().act(current, b"") == base.Agent().act(current, b""))
    check(any(e.kind == "prize_the_shover" for e in excluded[2].history))

    natural_support = 0
    for seed in range(240):
        current = state("premium-natural-" + str(seed), bb_hero=bool(seed % 2))
        percentile = sample._PREFLOP_COMBOS["".join(sorted(current.cards))][0]
        supported = sample.premium_small_open(current, sample.preflop_context(current), percentile)
        a, _ = base.Agent().act(current, b"")
        b, _ = sample.Agent().act(current, b"")
        c, _ = bet.Agent().act(current, b"")
        check(is_legal(b, current.legal_actions) and is_legal(c, current.legal_actions))
        if supported:
            natural_support += 1
            check(c.kind == "raise")
        else:
            check(a == b == c)
    check(natural_support > 0)
    print(json.dumps({"assertions": checks, "generated_states": 248,
                      "natural_premium_routes": natural_support, "failed": 0,
                      "hashes": {label: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for label, path in (("baseline", args.baseline), ("sampling", args.sampling),
                                                     ("threebet", args.threebet))}}, indent=2))


if __name__ == "__main__":
    main()
