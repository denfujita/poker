#!/usr/bin/env python3
"""Synthetic regressions for action-size range weighting and causal contexts."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
source_sha = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location('candidate', args.candidate)
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def event(kind, seat=None, amount=0, cards=()):
    return SimpleNamespace(kind=kind, seat=seat, amount=amount, cards=cards)


live = (SimpleNamespace(seat=1),)
board = ('Kc', '9d', '2s')
prefix = (event('blind', 0, 50), event('blind', 1, 50), event('board', cards=board))


def contexts(events):
    return candidate.opponent_ranges(SimpleNamespace(history=events), live)[0]


small = contexts(prefix + (event('raise', 1, 25),))
large = contexts(prefix + (event('raise', 1, 100),))
repeated = contexts(prefix + (event('raise', 1, 25), event('raise', 0, 75),
                              event('raise', 1, 100)))
strong = tuple(candidate._CARD[c] for c in ('3h', 'Kd'))
weak = tuple(candidate._CARD[c] for c in ('3h', '5c'))


def odds(ctx):
    return candidate._range_weight(strong, ctx) / candidate._range_weight(weak, ctx)


small_odds, large_odds, repeated_odds = odds(small), odds(large), odds(repeated)
assert large[0][0] > small[0][0] and repeated[0][0] > small[0][0]
assert large_odds > small_odds, (small_odds, large_odds)
assert repeated_odds > small_odds, (small_odds, repeated_odds)
strongest = ((4.5, tuple(candidate._CARD[c] for c in board)),)
weak_weight = candidate._range_weight(weak, strongest)
strong_weight = candidate._range_weight(strong, strongest)
assert 0 < weak_weight < strong_weight, (weak_weight, strong_weight)
later = contexts(prefix + (event('raise', 1, 100), event('call', 0, 100),
                            event('board', cards=('8h',)), event('raise', 0, 10),
                            event('call', 1, 10)))
assert len(later) == 2 and len(later[0][1]) == 4 and len(later[1][1]) == 3
assert later[1][0] == large[0][0], (later, large)
assert hashlib.sha256(args.candidate.read_bytes()).hexdigest() == source_sha
print(json.dumps(dict(
    candidate_sha256=source_sha,
    passed=4,
    value_to_air_odds=dict(small_bet=small_odds, large_bet=large_odds,
                           repeated_raise=repeated_odds),
    weak_to_value_ratio=weak_weight / strong_weight,
    historical_board_retained=True,
), indent=2))
