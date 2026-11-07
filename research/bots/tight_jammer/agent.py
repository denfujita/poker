"""Test opponent (not a submission): shoves only strong hands, otherwise check/fold.

Preflop: all-in with a pair of 9s or better among its 3 cards, or two of A/K; else check/fold.
Select: keep the best 2 cards for the current flop, expose the lower one.
Postflop: all-in with a pair using a hole card at least top-pair strength; else check/fold.
"""

import itertools

import eval7
import poker_agent_sdk
from poker_agent_sdk import Action

RANKS = "23456789TJQKA"


def strong_preflop(cards):
    ranks = sorted((RANKS.index(c[0]) for c in cards), reverse=True)
    pairs = [r for r in set(ranks) if ranks.count(r) >= 2]
    if pairs and max(pairs) >= RANKS.index("9"):
        return True
    return ranks[0] == 12 and ranks[1] >= 11  # AA handled above; AK


def strong_postflop(cards, board):
    hole = [eval7.Card(c) for c in cards]
    brd = [eval7.Card(c) for c in board]
    mine = eval7.evaluate(hole + brd)
    board_only = eval7.evaluate(brd) if len(brd) >= 5 else -1
    if mine <= board_only:
        return False
    hand_type = eval7.handtype(mine)
    if hand_type in ("Two Pair", "Trips", "Straight", "Flush", "Full House", "Quads", "Straight Flush"):
        return True
    if hand_type == "Pair":
        top = max(RANKS.index(c[0]) for c in board)
        return any(RANKS.index(c[0]) >= top and any(c[0] == b[0] for b in board) for c in cards) or (
            cards[0][0] == cards[1][0] and RANKS.index(cards[0][0]) > top
        )
    return False


class Agent(poker_agent_sdk.Agent):
    def act(self, state, memory):
        if state.phase == "select":
            best = max(
                itertools.combinations(range(3), 2),
                key=lambda pair: eval7.evaluate([eval7.Card(state.cards[i]) for i in pair] + [eval7.Card(b) for b in state.board]),
            )
            discard = next(i for i in range(3) if i not in best)
            reveal = min(best, key=lambda i: RANKS.index(state.cards[i][0]))
            return Action("select", cards=(discard, reveal)), memory
        if state.phase != "betting":
            first = state.legal_actions[0]
            return Action(first.kind, first.min_amount), memory
        strong = strong_preflop(state.cards) if not state.board else strong_postflop(state.cards, state.board)
        raise_ = state.can("raise")
        if strong and raise_:
            return Action.raise_to(raise_.max_amount), memory
        if strong and state.can("call"):
            return Action.call(), memory
        if state.can("check"):
            return Action.check(), memory
        return Action.fold(), memory
