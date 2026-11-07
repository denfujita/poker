#!/usr/bin/env python3
"""Real-engine SB jam -> prize event -> BB Agent.act regression.

Run with the official starter-kit environment. Uses generated hands only and
prints aggregate checks, never private tournament histories.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import sys

from poker_agent_protocol.game import Action, BlindLevel, is_legal
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant

sys.dont_write_bytecode = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate", type=Path)
    args = ap.parse_args()
    path = args.candidate.resolve()
    spec = importlib.util.spec_from_file_location("candidate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    variant = load_variant("flop_discard_reveal")
    cases = []
    for players in (2, 3, 4, 6, 8):
        table_id = f"jamfold-engine-award-{players}"
        table = SitAndGo(rules=TableRules(variant="flop_discard_reveal", players=players,
                                         starting_stack=200, blinds=(BlindLevel(10, 20),), hand_cap=1),
                         variant=variant, table_id=table_id, seed=table_id)
        state = table.decision()
        sb = next(e.seat for e in state.history if e.kind == "blind" and e.amount == 10)
        bb = next(e.seat for e in state.history if e.kind == "blind" and e.amount == 20)
        while state.seat != sb:
            assert state.seat != bb, "BB acted before folded-to SB"
            assert table.apply(Action.fold())
            state = table.decision()
        assert module.supported_jamfold_spot(state) is not None
        assert table.apply(Action.raise_to(state.can("raise").max_amount))
        state = table.decision()
        assert state.seat == bb
        kinds = tuple(event.kind for event in state.history)
        assert "prize_the_shover" in kinds
        assert kinds.index("raise") < kinds.index("prize_the_shover")
        spot = module.supported_jamfold_spot(state)
        assert spot is not None, "Non-chip award blocked the real BB chart decision"
        action, probability, kind, chart_players, depth = spot
        assert kind == "call" and chart_players == players and depth == 10
        seed = (f"jamfold-v1:{state.config.table_id}:{state.hand_number}:{state.seat}:"
                f"{chart_players}:{depth}:{kind}:{''.join(sorted(state.cards))}")
        expected = action if random.Random(seed).random() < probability else Action.fold()
        original_equities = module.equities
        def fail_fallthrough(*args, **kwargs):
            raise AssertionError("Actual BB chart decision fell through to equity")
        module.equities = fail_fallthrough
        actual, memory = module.Agent().act(state, b"invalid-memory")
        module.equities = original_equities
        assert actual == expected and memory == b""
        assert is_legal(actual, state.legal_actions)
        cases.append({"players": players, "award_before_bb": True, "chart_route_reached": True})
    print(json.dumps({"real_engine_cases": cases, "failed": 0}, indent=2))


if __name__ == "__main__":
    main()
