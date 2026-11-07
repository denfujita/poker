#!/usr/bin/env python3
"""Run reproducible, timed SDK matches and retain table-level statistics.

Run with the installed starter-kit virtualenv. Bot code runs through the same
BotPool/guest protocol as `poker-agent play`; this script is never uploaded.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import secrets
import statistics
import sys
import time

from poker_agent_protocol.process import BotPool
from poker_engine.play import play_table
from poker_engine.scoring import table_places, table_points
from poker_engine.seating import seat_iteration
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant
from poker_agent_sdk.history import HistoryWriter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wilson(successes: int, n: int) -> dict:
    if not n:
        return {"count": 0, "rate": None, "ci95": [None, None]}
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return {"count": successes, "rate": p, "ci95": [max(0.0, center - half), min(1.0, center + half)]}


def summarize_entry(records: list[dict], entry_index: int) -> dict:
    entries = [next(entry for entry in row["entries"] if entry["entry_index"] == entry_index) for row in records]
    points = [entry["points"] for entry in entries]
    n = len(points)
    mean = statistics.fmean(points) if n else None
    sd = statistics.stdev(points) if n > 1 else None
    se = sd / math.sqrt(n) if sd is not None else None
    failed = sum(entry["failed_decisions"] for entry in entries)
    decisions = sum(entry["decisions"] for entry in entries)
    return {
        "tables": n,
        "mean_points": mean,
        "sample_sd_points": sd,
        "standard_error_points": se,
        "mean_points_normal_ci95": [mean - 1.959963984540054 * se, mean + 1.959963984540054 * se] if se is not None else [None, None],
        "first_place": wilson(sum(entry["place"] == 1 for entry in entries), n),
        "top_three": wilson(sum(entry["place"] <= 3 for entry in entries), n),
        "positive_points": wilson(sum(entry["points"] > 0 for entry in entries), n),
        "outright_win": wilson(sum(entry["outright_win"] for entry in entries), n),
        "finishing_positions": dict(sorted(Counter(entry["place"] for entry in entries).items())),
        "failed_decisions": failed,
        "decisions": decisions,
        "failed_decision_rate": failed / decisions if decisions else None,
    }


async def run(args: argparse.Namespace) -> dict:
    bots = [path.resolve() for path in args.bots]
    if not 2 <= len(bots) <= 10 or not all((bot / "agent.py").is_file() for bot in bots):
        raise ValueError("Give 2–10 bot folders containing agent.py; the first is the candidate.")
    if args.tables < 1 or args.concurrency < 1 or not 0 <= args.hero < len(bots):
        raise ValueError("Invalid table count, concurrency, or hero index.")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists() or args.summary.exists() or (args.history and args.history.exists()):
        raise ValueError("Output, summary, or history already exists; use a new path to preserve earlier runs.")
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    if args.history:
        args.history.parent.mkdir(parents=True, exist_ok=True)
    seed = args.seed or secrets.token_hex(8)
    rules = TableRules(
        variant=args.variant,
        players=len(bots),
        decision_ms=args.decision_ms,
        time_bank_ms=args.time_bank_ms,
        hand_cap=args.hand_cap,
    )
    variant = load_variant(rules.variant)
    hashes = {str(bot): sha256(bot / "agent.py") for bot in set(bots)}
    if args.expected_sha256 and hashes[str(bots[args.hero])] != args.expected_sha256:
        raise ValueError("Candidate SHA-256 does not match --expected-sha256.")
    pools = {
        bot: BotPool([sys.executable, "-m", "poker_agent_sdk.guest", str(bot)], copies=2, cwd=str(bot))
        for bot in set(bots)
    }
    # Index labels permit exactly paired seating/deal seeds across candidate versions.
    labels = list(range(len(bots)))
    history_labels = [f"{bot.name}#{index}" for index, bot in enumerate(bots)]
    records: list[dict] = []
    semaphore = asyncio.Semaphore(args.concurrency)
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    completed = 0

    with ExitStack() as stack:
        raw = stack.enter_context(args.out.open("x"))
        history = stack.enter_context(HistoryWriter(args.history, labels=history_labels, hero=args.hero, seed=seed)) if args.history else None
        async def one_table(number: int) -> None:
            nonlocal completed
            async with semaphore:
                seating = seat_iteration(labels, seed=seed, iteration=number, table_size=len(bots))[0]
                table = SitAndGo(rules=rules, variant=variant, table_id=f"benchmark-{number}", seed=f"{seed}:{number}")
                result = await play_table(table, [pools[bots[assignment.entry]] for assignment in seating])
                if history is not None and number < args.history_tables:
                    # Use the SDK's participant-view export, including owner-only
                    # private events. Compress outside the timed host event loop.
                    await asyncio.to_thread(history.table, {
                        "variant": rules.variant,
                        "iteration": number,
                        "table": 0,
                        "seats": [history_labels[assignment.entry] for assignment in seating],
                        "fillers": [assignment.filler for assignment in seating],
                        "payouts": list(table.payouts),
                        "hands": table.log,
                    })
                points = table_points(result, table.payouts)
                places = table_places(result)
                survivors = sum(stack > 0 for stack in result.final_stacks)
                entries = []
                for seat, assignment in enumerate(seating):
                    entries.append({
                        "entry_index": assignment.entry,
                        "bot_name": bots[assignment.entry].name,
                        "seat": seat,
                        "points": points[seat],
                        "place": places[seat],
                        "final_stack": result.final_stacks[seat],
                        "failed_decisions": result.failures[seat],
                        "decisions": result.decisions[seat],
                        "outright_win": survivors == 1 and result.final_stacks[seat] > 0,
                    })
                candidate = next(entry for entry in entries if entry["entry_index"] == args.hero)
                row = {
                    "iteration": number,
                    "table_index": number,
                    "table_seed": f"{seed}:{number}",
                    "payouts": list(table.payouts),
                    "hands": result.hands_played,
                    "hand_cap_stop": result.hands_played >= rules.hand_cap and survivors > 1,
                    "survivors": survivors,
                    "candidate": candidate,
                    "entries": entries,
                }
                records.append(row)
                raw.write(json.dumps(row, separators=(",", ":")) + "\n")
                raw.flush()
                completed += 1
                if completed % args.progress_every == 0 or completed == args.tables:
                    print(json.dumps({"completed": completed, "total": args.tables, "elapsed_seconds": round(time.perf_counter() - started, 2)}), file=sys.stderr, flush=True)

        tasks = [asyncio.create_task(one_table(i)) for i in range(args.tables)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for pool in pools.values():
                await pool.stop()

    records.sort(key=lambda row: row["iteration"])
    pool_stderr = {str(bot): pool.logs.decode(errors="replace") for bot, pool in pools.items() if pool.logs}
    all_entry_stats = {str(index): {"bot_folder": str(bot), **summarize_entry(records, index)} for index, bot in enumerate(bots)}
    unchanged = all(sha256(bot / "agent.py") == hashes[str(bot)] for bot in set(bots))
    summary = {
        "started_at_utc": started_at,
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "seed": seed,
        "tables": len(records),
        "concurrency": args.concurrency,
        "rules": asdict(rules),
        "bot_folders": [str(bot) for bot in bots],
        "bot_sha256": hashes,
        "candidate_index": args.hero,
        "candidate_sha256": hashes[str(bots[args.hero])],
        "input_files_unchanged": unchanged,
        "candidate": all_entry_stats[str(args.hero)],
        "all_entries": all_entry_stats,
        "average_hands": statistics.fmean(row["hands"] for row in records),
        "hand_cap_count": sum(row["hand_cap_stop"] for row in records),
        "all_bots_failed_decisions": sum(entry["failed_decisions"] for row in records for entry in row["entries"]),
        "all_bots_decisions": sum(entry["decisions"] for row in records for entry in row["entries"]),
        "bot_stderr": pool_stderr,
        "raw_tables_path": str(args.out.resolve()),
        "history_path": str(args.history.resolve()) if args.history else None,
        "history_tables_saved": min(args.tables, args.history_tables) if args.history else 0,
        "statistical_notes": [
            "The independent sampling unit is one candidate table; confidence intervals are unadjusted 95% intervals.",
            "Mean-points intervals use raw ICM-aware table points, sample SD, and a normal approximation.",
            "First-place, top-three, and outright-win intervals use Wilson binomial intervals.",
            "At the hand cap, places rank surviving stacks; first place can be a chip lead rather than an outright win.",
            "These results describe this fixed reference-bot field, not the unknown tournament field.",
        ],
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not unchanged:
        raise RuntimeError("A bot source changed during the run; results must not be attributed to one fixed version.")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bots", nargs="+", type=Path)
    parser.add_argument("--tables", type=int, default=200)
    parser.add_argument("--seed")
    parser.add_argument("--hero", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--variant", default="flop_discard_reveal")
    parser.add_argument("--decision-ms", type=int, default=1)
    parser.add_argument("--time-bank-ms", type=int, default=100)
    parser.add_argument("--hand-cap", type=int, default=250)
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--history", type=Path, help="Save a participant-format .jsonl.gz sample for replay/analysis.")
    parser.add_argument("--history-tables", type=int, default=20, help="Save the first N table indexes when --history is given (default20).")
    args = parser.parse_args()
    args.summary = args.summary or args.out.with_suffix(".summary.json")
    if args.progress_every < 1:
        parser.error("--progress-every must be positive")
    if args.history_tables < 1:
        parser.error("--history-tables must be positive")
    try:
        asyncio.run(run(args))
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
