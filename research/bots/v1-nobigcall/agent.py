"""A small equity / pot-odds baseline for the Bay Area discard-and-reveal variant.

This is a chip-EV heuristic, not a GTO or ICM solver. Opponents have uniformly
random two-card hands; their exposed cards and discard-selection skill are not
modeled. Repeated raises add a conservative margin, not an inferred posterior.
All game-dependent work is local to a decision; no cross-table state is kept.
"""

import random

import eval7
import poker_agent_sdk
from poker_agent_sdk import Action, GameState


_TEXT = tuple(rank + suit for rank in "23456789TJQKA" for suit in "cdhs")
_DECK = tuple(eval7.Card(card) for card in _TEXT)
_CARD = dict(zip(_TEXT, _DECK))
_INDEX = {card: index for index, card in enumerate(_TEXT)}
_EVALUATE = eval7.evaluate
# Initialize the evaluator before the first timed decision.
_EVALUATE(list(_DECK[:7]))


def equities(cards, board, opponents, discarded=()):
    """Return showdown pot shares for each possible discard (or the sole pair).

For three cards, result[i] is equity after discarding original card i. Choose
the best AVERAGE; choosing the best pair on each future board is clairvoyant.
Preflop this estimates the best fixed pair, conservatively ignoring the option
to change our selection after seeing the flop. Ties split among all winners.
"""
    hole = tuple(_CARD[c] for c in cards)
    community = tuple(_CARD[c] for c in board)
    dead = tuple(_CARD[c] for c in discarded)
    hands = ((hole[1], hole[2]), (hole[0], hole[2]), (hole[0], hole[1])) if len(hole) == 3 else (hole,)
    if opponents == 0:
        return (1.0,) * len(hands)
    blocked = set(hole + community + dead)
    deck = [card for card in _DECK if card not in blocked]
    # Per-state deterministic sampling: reproducible across processes and no
    # mutable global RNG, caches, or information carried between tables.
    seed = 2166136261
    for card in sorted(set(cards) | set(board) | set(discarded)):
        seed = ((seed ^ (_INDEX[card] + 1)) * 16777619) & 0xFFFFFFFF
    seed ^= opponents * 104729
    sample = random.Random(seed).sample
    missing = 5 - len(community)
    draws = missing + 2 * opponents
    samples = 48 if opponents <= 3 else 32
    totals = [0.0] * len(hands)
    for _ in range(samples):
        picked = sample(deck, draws)
        completed = community + tuple(picked[:missing])
        scores = [
            _EVALUATE(completed + (picked[missing + 2 * j], picked[missing + 2 * j + 1]))
            for j in range(opponents)
        ]
        best = max(scores)
        for i, hand in enumerate(hands):
            value = _EVALUATE(completed + hand)
            if value > best:
                totals[i] += 1.0
            elif value == best:
                totals[i] += 1.0 / (1 + scores.count(best))
    return tuple(value / samples for value in totals)


def contributions(state):
    """Reconstruct per-hand commitments; raise events contain STREET totals."""
    total = {seat.seat: 0 for seat in state.seats}
    street = {seat.seat: 0 for seat in state.seats}
    for event in state.history:
        if event.kind == "board":
            street = dict.fromkeys(street, 0)
        elif event.seat in total:
            seat = event.seat
            if event.kind == "ante":
                total[seat] += event.amount
            elif event.kind in ("blind", "call"):
                total[seat] += event.amount
                street[seat] += event.amount
            elif event.kind == "raise":
                added = max(0, event.amount - street[seat])
                total[seat] += added
                street[seat] = event.amount
    return total


def eligible_pot(state, committed, hero_cost, additions=None):
    """Post-action pot hero can win, excluding commitments above hero's cap."""
    additions = additions or {}
    cap = committed[state.seat] + hero_cost
    pot = cap + sum(
        min(amount + additions.get(seat, 0), cap)
        for seat, amount in committed.items() if seat != state.seat
    )
    # The public event stream does not identify every uncalled refund. Never
    # count more than the actual pot plus newly committed chips.
    return min(pot, state.pot + hero_cost + sum(additions.values()))


def pressure_margin(state, live, cost):
    """A small caution margin for repeated aggression, not opponent learning."""
    raises = 0
    for event in state.history:
        if event.kind == "board":
            raises = 0
        elif event.kind == "raise" and event.seat in live:
            raises += 1
    margin = 0.015 + min(0.045, 0.015 * max(0, raises - 1))
    if cost > state.pot / 2:
        margin += 0.025
    return margin


def decide(state: GameState) -> Action:
    live = [seat for seat in state.seats if seat.seat != state.seat and seat.status in ("active", "all_in")]
    if state.phase not in ("select", "betting"):
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)

    values = equities(state.cards, state.board, len(live), state.variant.get("discarded", ()))
    if state.phase == "select":
        discard = max(range(3), key=lambda index: values[index])
        retained = [index for index in range(3) if index != discard]
        # Revealing either retained card has identical showdown equity. Expose
        # the lower rank as a simple information heuristic, not an EV claim.
        reveal = min(retained, key=lambda index: _INDEX[state.cards[index]])
        return Action("select", cards=(discard, reveal))

    hero = next(seat for seat in state.seats if seat.seat == state.seat)
    check = state.can("check")
    call = state.can("call")
    cost = min(max(0, state.to_call), hero.stack) if call else 0
    committed = contributions(state)
    equity = max(0.0, max(values) - pressure_margin(state, {seat.seat for seat in live}, cost))
    passive_ev = equity * eligible_pot(state, committed, cost) - cost
    passive = Action.check() if check else Action.call() if call and passive_ev >= 0 else Action.fold()
    # DIAGNOSTIC ONLY: refuse calls costing >= 25% of our chips unless very strong vs random.
    if passive.kind == "call" and cost >= 0.25 * (hero.stack + hero.bet) and max(values) < 0.75:
        passive = Action.fold()

    raise_ = state.can("raise")
    callers = [seat for seat in live if seat.status == "active" and seat.stack > 0]
    if raise_ and callers:
        # One half-pot value size, expressed as TOTAL street commitment.
        target = hero.bet + cost + max(1, (state.pot + cost) // 2)
        cover = max(seat.bet + seat.stack for seat in callers)
        target = int(min(raise_.max_amount, cover, max(raise_.min_amount, target)))
        if target >= raise_.min_amount:
            raise_cost = target - hero.bet
            additions = {seat.seat: min(seat.stack, max(0, target - seat.bet)) for seat in callers}
            # Deliberately no assumed fold equity or arbitrary bluff mixture:
            # this simple model projects all live opponents continuing.
            value_equity = max(0.0, equity - 0.025)
            raise_ev = value_equity * eligible_pot(state, committed, raise_cost, additions) - raise_cost
            if (value_equity > 1.0 / (len(live) + 1) + 0.08
                    and raise_ev > max(0.0, passive_ev) + 0.05 * raise_cost):
                return Action.raise_to(target)

    if passive.kind == "fold" and not state.can("fold"):
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)
    return passive


class Agent(poker_agent_sdk.Agent):
    def act(self, state: GameState, memory: bytes) -> tuple[Action, bytes]:
        # The public current-hand history supplies all information this first
        # baseline uses. Ignoring memory also makes truncated/invalid bytes safe.
        return decide(state), b""
