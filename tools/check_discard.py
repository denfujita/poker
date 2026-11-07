#!/usr/bin/env python3
"""Check synthetic discard permutations and preserve a higher-equity draw."""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('candidate', type=Path)
args = parser.parse_args()
source_sha = hashlib.sha256(args.candidate.read_bytes()).hexdigest()
spec = importlib.util.spec_from_file_location('candidate', args.candidate)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def selection_state(cards, board, opponents):
    return SimpleNamespace(
        phase='select', cards=cards, board=board, seat=0, variant={}, history=[],
        pot=0, to_call=0, can=lambda kind: None,
        seats=[SimpleNamespace(seat=i, status='active', shown_cards=(), stack=1000, bet=0)
               for i in range(opponents + 1)],
    )


# Constructed cases: two full houses, quads with the best kicker, a royal flush.
cases = [
    (('6d', 'Jd', '3s'), ('6s', 'Jh', '6c'), '3s'),
    (('Kh', '5h', '8h'), ('5d', '5c', 'Ks'), '8h'),
    (('8d', 'Kd', '3s'), ('8s', '8h', '8c'), '3s'),
    (('Qh', 'Jh', '2d'), ('Ah', 'Kh', 'Th'), '2d'),
]
errors = []
checked = 0
for original, board, expected in cases:
    for cards in itertools.permutations(original):
        for opponents in (1, 2, 3, 7, 9):
            action = bot.decide(selection_state(cards, board, opponents))
            discard, reveal = action.cards
            checked += 1
            if (action.kind != 'select' or action.amount != 0
                    or type(discard) is not int or type(reveal) is not int
                    or not 0 <= discard < 3 or not 0 <= reveal < 3
                    or discard == reveal or cards[discard] != expected):
                errors.append(dict(cards=cards, board=board, opponents=opponents,
                                   expected=expected, action=repr(action)))

# On this board the unique sampled winner is the royal/flush/straight draw,
# despite another pair making a stronger current hand. Do not override its EV.
for cards in itertools.permutations(('Qh', 'Jh', '2d')):
    board = ('Ah', 'Kh', '2c')
    values = bot.equities(cards, board, 1)
    action = bot.decide(selection_state(cards, board, 1))
    checked += 1
    best = max(range(3), key=lambda i: values[i])
    if values.count(max(values)) != 1 or action.cards[0] != best:
        errors.append(dict(draw_equities=values, action=repr(action)))

assert hashlib.sha256(args.candidate.read_bytes()).hexdigest() == source_sha
print(json.dumps(dict(candidate_sha256=source_sha, checked=checked, failures=errors), indent=2))
raise SystemExit(bool(errors))
