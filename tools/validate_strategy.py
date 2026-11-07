#!/usr/bin/env python3
"""Real-engine legality, memory robustness, and act latency checks for a bot.

Run with the starter-kit virtualenv. This is test tooling, never a bot upload.
End-to-end deadline enforcement remains the SDK play command's responsibility.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import random
import statistics
import sys
import time

from poker_agent_protocol.game import (
    Action, GameState, action_from_dict, is_legal, state_from_dict, state_to_dict,
)
from poker_agent_sdk.guest import reply
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant


VARIANT = "flop_discard_reveal"


def street(state: GameState) -> str:
    return "select" if state.phase == "select" else {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(state.board)]


def policy(state: GameState, mode: str) -> Action:
    if state.phase == "select":
        # Cycle all six legal ordered pairs across real cards.
        pairs = ((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1))
        return Action("select", cards=pairs[(state.hand_number + state.seat) % 6])
    legal_raise = state.can("raise")
    if mode == "jam" and legal_raise and len(state.board) == (0 if state.hand_number % 2 else 3):
        return Action.raise_to(legal_raise.max_amount)
    if mode == "raise" and legal_raise:
        current = []
        for event in reversed(state.history):
            if event.kind == "board":
                break
            current.append(event)
        if sum(event.kind == "raise" for event in current) < 2:
            return Action.raise_to(min(legal_raise.max_amount, max(legal_raise.min_amount, state.pot)))
    if state.can("check"):
        return Action.check()
    if state.can("call"):
        return Action.call()
    return Action.fold()


def collect_fixtures() -> tuple[list[GameState], dict]:
    fixtures: list[GameState] = []
    buckets = Counter()
    visited = 0
    variant = load_variant(VARIANT)
    for players in (2, 3, 8, 10):
        for mode in ("call", "raise", "jam"):
            for replicate in range(2):
                table = SitAndGo(
                    rules=TableRules(variant=VARIANT, players=players, hand_cap=14),
                    variant=variant,
                    table_id=f"fixtures-{players}-{mode}-{replicate}",
                    seed=f"baseline-fixtures-v1:{players}:{mode}:{replicate}",
                )
                if mode == "jam":
                    # Legal in-play unequal stacks create short all-in calls and side pots.
                    table.stacks = [2000, 183, 71, 39, 1000, 400, 79, 2000, 103, 43][:players]
                while (state := table.decision()) is not None:
                    me = next(seat for seat in state.seats if seat.seat == state.seat)
                    bucket = (
                        players, mode, street(state), bool(state.to_call),
                        bool(state.to_call > me.stack),
                        any(seat.status == "all_in" for seat in state.seats),
                    )
                    if buckets[bucket] < 5:
                        # Copy through the actual wire representation, so later table mutation
                        # cannot alter fixtures and state shapes match the guest entry point.
                        fixtures.append(state_from_dict(state_to_dict(state)))
                        buckets[bucket] += 1
                    assert table.apply(policy(state, mode)), "Fixture policy produced illegal action"
                    visited += 1
    coverage = {
        "generated_decisions": visited,
        "fixture_count": len(fixtures),
        "by_street": dict(Counter(street(s) for s in fixtures)),
        "by_player_count": dict(Counter(s.config.players for s in fixtures)),
        "short_all_in_call_states": sum(s.to_call > next(p.stack for p in s.seats if p.seat == s.seat) for s in fixtures),
        "all_in_select_states": sum(s.phase == "select" and next(p.status for p in s.seats if p.seat == s.seat) == "all_in" for s in fixtures),
        "known_own_discard_states": sum(bool(s.variant.get("discarded")) for s in fixtures),
        "opponent_exposure_states": sum(any(p.shown_cards for p in s.seats if p.seat != s.seat) for s in fixtures),
    }
    assert coverage["short_all_in_call_states"] > 0
    assert coverage["all_in_select_states"] > 0
    assert set(coverage["by_street"]) == {"preflop", "select", "flop", "turn", "river"}
    return fixtures, coverage


def load_candidate(path: Path):
    path = path.resolve()
    if path.is_dir():
        path /= "agent.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("validation_candidate", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load candidate: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_reply(state: GameState, result) -> tuple[Action, bytes]:
    wire_action, memory = reply(result)
    action = action_from_dict(wire_action)
    assert is_legal(action, state.legal_actions), (street(state), action, state.legal_actions)
    if action.kind == "select":
        # Empty cards is the legal fallback, but a strategy can use an explicit pair.
        pair = action.cards or (2, 0)
        assert action.amount == 0
        assert len(state.cards) == 3
        assert len(pair) == 2 and pair[0] != pair[1] and all(type(i) is int and 0 <= i <= 2 for i in pair)
    elif action.kind == "raise":
        limits = state.can("raise")
        assert type(result[0].amount) is int, "Strategy raises should use whole chips before wire normalization"
        assert limits.min_amount <= action.amount <= limits.max_amount
    else:
        assert action.amount == 0 and not action.cards
    # Match real guest truncation, rather than incorrectly treating long returned memory
    # as an illegal reply. The next robustness tests feed truncations back to the bot.
    return action, memory[:state.config.memory_bytes]


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * q))]


def summary(values: list[float]) -> dict:
    return {
        "n": len(values),
        "p50_us": round(statistics.median(values), 3),
        "p99_us": round(percentile(values, .99), 3),
        "max_us": round(max(values), 3),
        "over_1ms": sum(value > 1000 for value in values),
    }


def run(candidate: Path, fixtures: list[GameState], repeats: int) -> dict:
    module = load_candidate(candidate)
    agent = module.Agent()
    cold = {}
    actions = Counter()
    memories = []
    for state in fixtures:
        start = time.perf_counter_ns()
        result = agent.act(state, b"")
        elapsed = (time.perf_counter_ns() - start) / 1000
        cold.setdefault(street(state), elapsed)
        action, memory = validate_reply(state, result)
        actions[action.kind] += 1
        memories.append(memory)

    # A truncated memory is sent back unchanged after failures, so it must not poison all
    # subsequent decisions. Cover non-UTF8, invalid JSON, zero-byte and tiny table limits.
    malformed = (b"", b"{", b"\xff", b"\x00" * 9, b"[]", b"null", b"{\"x\":", b"x" * 65536)
    memory_checks = 0
    representative = {}
    for state, memory in zip(fixtures, memories):
        representative.setdefault(street(state), (state, memory))
    for state, returned in representative.values():
        inputs = list(malformed) + [returned[:k] for k in (0, 1, max(0, len(returned) // 2), max(0, len(returned) - 1))]
        for memory in inputs:
            validate_reply(state, agent.act(state, memory))
            memory_checks += 1
        for limit in (0, 1, 16):
            tiny = replace(state, config=replace(state.config, memory_bytes=limit))
            _, trimmed = validate_reply(tiny, agent.act(tiny, returned[:limit]))
            validate_reply(tiny, agent.act(tiny, trimmed))
            memory_checks += 2

    # Benchmark after correctness checks, outside engine/serialization/validation overhead.
    # Include returned memory to measure parsing, and vary order to avoid one-state bias.
    order = list(range(len(fixtures)))
    random.Random(20261106).shuffle(order)
    timings = defaultdict(list)
    for _ in range(repeats):
        for index in order:
            state = fixtures[index]
            start = time.perf_counter_ns()
            agent.act(state, memories[index])
            timings[street(state)].append((time.perf_counter_ns() - start) / 1000)
    return {
        "candidate": str(candidate.resolve()),
        "action_counts": dict(actions),
        "legality_checks": len(fixtures),
        "memory_robustness_checks": memory_checks,
        "first_call_by_street_us": {name: round(value, 3) for name, value in cold.items()},
        "act_latency": {name: summary(values) for name, values in sorted(timings.items())},
        "act_latency_overall": summary([v for values in timings.values() for v in values]),
        "latency_scope": "act only; excludes wire and host delivery. Run SDK play for end-to-end deadlines.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", nargs="?", type=Path)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--fixtures-out", type=Path)
    parser.add_argument("--fixtures-in", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.fixtures_in:
        payload = json.loads(args.fixtures_in.read_text())
        fixtures = [state_from_dict(item) for item in payload["states"]]
        coverage = payload["coverage"]
    else:
        fixtures, coverage = collect_fixtures()
    if args.fixtures_out:
        args.fixtures_out.write_text(json.dumps({"coverage": coverage, "states": [state_to_dict(s) for s in fixtures]}))
    report = {"coverage": coverage}
    if args.candidate:
        report.update(run(args.candidate, fixtures, args.repeats))
    output = json.dumps(report, indent=2)
    if args.report:
        args.report.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
