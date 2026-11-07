#!/usr/bin/env python3
"""Heads-up short matches through normal SDK guest processes, with zero time bank.

Run using the installed starter-kit virtualenv. Does not modify the SDK or bots.
BotPool's default clean environment and delivery allowance match local CLI play.
This is a local upload-like timing probe, not the server's actual upload validator.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from poker_agent_protocol.process import BotPool
from poker_engine.play import play_table
from poker_engine.table import SitAndGo, TableRules
from poker_engine.variant import load_variant


async def run(args):
    candidate = args.candidate.resolve()
    opponent = args.opponent.resolve()
    for directory in (candidate, opponent):
        if not (directory / 'agent.py').is_file():
            raise ValueError(f'No agent.py in {directory}')
    paths = {'candidate': candidate, 'opponent': opponent}
    # Do not pass env: BotPool defaults to CLEAN_ENV, exactly as poker-agent play.
    pools = {
        name: BotPool([sys.executable, '-m', 'poker_agent_sdk.guest', str(path)], copies=2, cwd=str(path))
        for name, path in paths.items()
    }
    rules = TableRules(
        variant=args.variant,
        players=2,
        decision_ms=args.decision_ms,
        time_bank_ms=0,
        hand_cap=args.hand_cap,
    )
    variant = load_variant(args.variant)
    totals = {name: {'decisions': 0, 'failed_decisions': 0} for name in paths}
    records = []
    try:
        # Sequential tables avoid conflating no-bank readiness with synthetic host overload.
        # Each table resets memory/time banks, while the two-copy pools remain alive.
        for number in range(args.tables):
            labels = ['candidate', 'opponent'] if number % 2 == 0 else ['opponent', 'candidate']
            table = SitAndGo(rules=rules, variant=variant, table_id=f'no-bank-{number}', seed=f'{args.seed}:{number}')
            result = await play_table(table, [pools[name] for name in labels])
            record = {'table': number, 'hands': result.hands_played}
            for seat, label in enumerate(labels):
                stats = {'decisions': result.decisions[seat], 'failed_decisions': result.failures[seat]}
                record[label] = stats
                for key, value in stats.items():
                    totals[label][key] += value
            records.append(record)
    finally:
        await asyncio.gather(*(pool.stop() for pool in pools.values()))
    for values in totals.values():
        values['failure_rate'] = values['failed_decisions'] / values['decisions'] if values['decisions'] else None
    report = {
        'candidate': str(candidate),
        'opponent': str(opponent),
        'variant': args.variant,
        'tables': args.tables,
        'hand_cap': args.hand_cap,
        'decision_ms': args.decision_ms,
        'time_bank_ms': 0,
        'seed': args.seed,
        'guest_environment': 'SDK BotPool default CLEAN_ENV; two copies per bot; default delivery allowance',
        'scope': 'Local upload-like probe; not the competition upload validator',
        'totals': totals,
        'generations': {name: pool.generations() for name, pool in pools.items()},
        'errors': {name: pool.take_errors() for name, pool in pools.items()},
        'stderr': {name: pool.logs.decode(errors='replace')[-65536:] for name, pool in pools.items()},
        'per_table': records,
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('candidate', type=Path, help='Candidate bot directory containing agent.py')
    parser.add_argument('opponent', type=Path, help='Opponent bot directory, normally examples/check_or_fold')
    parser.add_argument('--tables', type=int, default=10)
    parser.add_argument('--hand-cap', type=int, default=20)
    parser.add_argument('--decision-ms', type=int, default=1)
    parser.add_argument('--variant', default='flop_discard_reveal')
    parser.add_argument('--seed', default='basic-equity-zero-bank-v1')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.tables < 1:
        parser.error('--tables must be positive')
    report = asyncio.run(run(args))
    output = json.dumps(report, indent=2)
    print(output)
    if args.report:
        args.report.write_text(output + '\n')
    # Keep errors meaningful even if a process problem is hidden by passive fallback.
    bad = any(x['failed_decisions'] for x in report['totals'].values()) or any(report['errors'].values())
    raise SystemExit(1 if bad else 0)


if __name__ == '__main__':
    main()
