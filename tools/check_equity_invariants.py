#!/usr/bin/env python3
"""Focused correctness checks for the basic-equity-v1 estimator and pot model."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys

from poker_agent_protocol.game import Event, state_from_dict
from validate_strategy import collect_fixtures, load_candidate, validate_reply

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('candidate', type=Path)
parser.add_argument('--fixtures-in', type=Path, help='Reuse generated fixture states, or generate them when omitted.')
parser.add_argument('--report', type=Path)
args = parser.parse_args()
candidate = args.candidate
module = load_candidate(candidate)
if args.fixtures_in:
    states = [state_from_dict(x) for x in json.loads(args.fixtures_in.read_text())['states']]
else:
    states, _ = collect_fixtures()
checks = []

# A royal flush entirely on the board ties every surviving player. Splits must
# account for the number of winners jointly, not raise heads-up equity to N.
for players in (2, 8, 10):
    for cards in [('2c', '3d'), ('2c', '3d', '4s')]:
        values = module.equities(cards, ('Ah', 'Kh', 'Qh', 'Jh', 'Th'), players - 1)
        assert all(math.isclose(x, 1 / players, abs_tol=1e-12) for x in values), (players, values)
        checks.append(f'board royal tie, {players} players, {len(cards)} hole cards')

# With J♥ T♥ on A♥ K♥ Q♥, retaining both suited cards makes an unbeatable royal.
selection = next(s for s in states if s.phase == 'select' and s.config.players == 8)
selection = replace(selection, cards=('Jh', 'Th', '2c'), board=('Ah', 'Kh', 'Qh'))
action, _ = validate_reply(selection, module.Agent().act(selection, b''))
values = module.equities(selection.cards, selection.board, 7)
assert values[2] == 1.0 and values[0] < values[2] and values[1] < values[2], values
assert action.kind == 'select' and action.cards[0] == 2 and action.cards[1] in (0, 1), action
checks.append('selection retains made royal and uses original discard/reveal indexes')

# Instrument exactly the sampling boundary; blockers must be absent from every
# simulation deck and draws cannot duplicate a card. No candidate source edits.
real_random = module.random.Random
sample_calls = []
blocked_cards = set()

class AuditedRandom(real_random):
    def sample(self, population, k, *args, **kwargs):
        assert not (set(population) & blocked_cards), 'Known hero/board/discard card in sampling deck'
        picked = super().sample(population, k, *args, **kwargs)
        assert len(set(picked)) == len(picked), 'Duplicate card in simulated deal'
        sample_calls.append((len(population), k))
        return picked

try:
    module.random.Random = AuditedRandom
    for cards, board, discarded, opponents in [
        (('As', 'Ad', '2c'), ('Ah', 'Ks', 'Qd'), (), 7),
        (('As', 'Ad'), ('Ah', 'Ks', 'Qd'), ('2c',), 7),
        (('As', 'Ad'), ('Ah', 'Ks', 'Qd', 'Tc'), ('2c',), 1),
        (('As', 'Ad', '2c'), (), (), 9),
    ]:
        blocked_cards = {module._CARD[x] for x in (*cards, *board, *discarded)}
        before = len(sample_calls)
        module.equities(cards, board, opponents, discarded)
        assert len(sample_calls) > before
        assert all(n == 52 - len(blocked_cards) for n, _ in sample_calls[before:])
    checks.append(f'hero cards, board and own discard excluded across {len(sample_calls)} sampled worlds; no duplicated draws')
finally:
    module.random.Random = real_random

# No opponent is eligible to beat a sole remaining player.
assert module.equities(('As', 'Ad'), (), 0) == (1.0,)
assert module.equities(('As', 'Ad', '2c'), (), 0) == (1.0, 1.0, 1.0)
checks.append('zero-opponent equity is exactly 1 for every retained-pair choice')

# Raises record a STREET total; calls/blinds record chip increments; antes do
# not count toward street bets. Subsequent streets start their raise totals at0.
base = next(s for s in states if s.config.players == 3 and s.phase == 'betting')
hero = base.seat
other = next(p.seat for p in base.seats if p.seat != hero)
third = next(p.seat for p in base.seats if p.seat not in (hero, other))
history = (
    Event('ante', hero, 2), Event('ante', other, 2), Event('ante', third, 2),
    Event('blind', hero, 10), Event('blind', other, 20),
    Event('raise', hero, 60), Event('call', other, 40),
    Event('board', cards=('Ah', 'Ks', 'Qd')),
    Event('raise', other, 100), Event('call', hero, 100),
    Event('board', cards=('Tc',)),
    Event('raise', hero, 150), Event('raise', other, 300), Event('call', hero, 150),
)
model = replace(base, history=history, pot=926)
expected = {hero: 462, other: 462, third: 2}
assert module.contributions(model) == expected, module.contributions(model)
checks.append('ante/blind/call accounting and street-total raises reconstruct commitments')

# Hero has committed100 and can add only50. The excess above150 from deeper
# opponents is an ineligible side pot; including it would encourage bad calls.
model = replace(base, pot=1400)
committed = {hero: 100, other: 600, third: 700}
assert module.eligible_pot(model, committed, 50) == 450
assert module.eligible_pot(model, committed, 0) == 300
checks.append('short-stack hero eligibility caps each seat at hero total, excludes side pots')

# Projected future callers add chips but remain subject to hero's cap; aggregate
# estimate cannot exceed the actual pot plus the proposed new commitments.
model = replace(base, pot=120)
committed = {hero: 20, other: 40, third: 60}
assert module.eligible_pot(model, committed, 80, {other: 60, third: 40}) == 300
model_refund = replace(model, pot=90)
assert module.eligible_pot(model_refund, committed, 80, {other: 60, third: 40}) == 270
checks.append('projected callers and actual-pot cap handle new chips and stale refund totals')

# Reproduction across calls must not depend on global table state.
input_args = (('As', 'Kh', '2c'), ('Ah', '7s', 'Qd'), 7)
one = module.equities(*input_args)
module.equities(('4s', '5s'), ('6s', 'Td', '9h'), 1, ('2d',))
two = module.equities(*input_args)
assert one == two, (one, two)
checks.append('per-state equity sampling is reproducible after an unrelated table decision')

report = {'candidate': str(candidate.resolve()), 'passed': len(checks), 'checks': checks}
print(json.dumps(report, indent=2))
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+'\n')
