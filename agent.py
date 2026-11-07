"""A small equity / pot-odds baseline for the Bay Area discard-and-reveal variant.

This is a chip-EV heuristic, not a GTO or ICM solver. Opponent exposed cards are fixed; unknown cards are sampled without replacement.
Folded public cards and our discard are removed. Public actions and bet sizes weight opponent hand hypotheses. This is a
value-heavy heuristic with a nonzero bluff likelihood, not a calibrated solver.
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


def opponent_ranges(state, live):
    """At most two action contexts per opponent, retaining earlier aggression.

    Each context uses its historical board and wager divided by the pot BEFORE
    that action. Repeated raises increase pressure. Keep the latest street and
    the strongest earlier street, so a later small call cannot erase a big raise.
    """
    wanted = {seat.seat for seat in live}
    by_seat = {seat: {} for seat in wanted}
    board = (); pot = 0; street_bets = {}; raises = {}
    for event in state.history:
        kind, seat, amount = event.kind, event.seat, event.amount
        if kind == "board":
            board += tuple(_CARD[c] for c in event.cards)
            street_bets = {}; raises = {}
        elif kind in ("ante", "blind", "call", "raise"):
            added = max(0, amount - street_bets.get(seat, 0)) if kind == "raise" else amount
            if seat in wanted and kind in ("call", "raise"):
                ratio = min(4.0, added / max(1, pot))
                if kind == "raise":
                    raises[seat] = raises.get(seat, 0) + 1
                    intensity = min(4.5, 1.0 + 1.25 * ratio + .5 * (raises[seat] - 1))
                else:
                    intensity = min(2.0, .25 + .75 * ratio)
                previous = by_seat[seat].get(len(board))
                if previous is None or intensity > previous[0]:
                    by_seat[seat][len(board)] = (intensity, board)
            pot += added
            if kind != "ante":
                street_bets[seat] = street_bets.get(seat, 0) + added
    result = []
    for seat in live:
        contexts = by_seat[seat.seat]
        if not contexts:
            result.append(())
            continue
        latest = max(contexts)
        current = contexts[latest]
        earlier = [value for street, value in contexts.items() if street != latest]
        result.append((current, max(earlier, key=lambda value: value[0])) if earlier else (current,))
    return tuple(result)


def _hand_strength(hand, board):
    """Cheap range-likelihood feature, not a second equity simulation."""
    first, second = hand
    r0, r1 = first.rank + 2, second.rank + 2
    if not board:
        if r0 == r1:
            return min(1.0, .60 + r0 / 35.0)
        return min(.93, .08 + .67 * (r0 + r1 - 4) / 24.0
                   + .07 * (first.suit == second.suit)
                   + .03 * (abs(r0 - r1) <= 2))
    category = _EVALUATE(board + hand) >> 24
    if category >= 4:
        return .98
    if category == 3:
        return .91
    board_ranks = tuple(card.rank + 2 for card in board)
    involved = r0 == r1 or r0 in board_ranks or r1 in board_ranks
    if category == 2:
        strength = .80 if involved else .19
    elif category == 1:
        paired_rank = max(r0 if r0 in board_ranks else 0,
                          r1 if r1 in board_ranks else 0,
                          r0 if r0 == r1 else 0)
        # Top pair/overpairs get more weight than bottom pair; board-only pairs
        # do not count as a held value hand.
        strength = (.49 + .22 * (paired_rank >= max(board_ranks))) if involved else .17
    else:
        strength = .10 + .10 * max(r0, r1) / 14.0
    if len(board) < 5:
        suits = tuple(card.suit for card in board) + (first.suit, second.suit)
        if suits.count(first.suit) >= 4 or suits.count(second.suit) >= 4:
            strength += .16
    return min(.95, strength)


def _range_weight(hand, contexts):
    # A positive strength floor retains weak hands and bluffs before exponentiation. It is not
    # claimed to equal a calibrated 10% posterior bluff frequency.
    weight = 1.0
    for intensity, action_board in contexts:
        strength = _hand_strength(hand, action_board)
        weight *= (.10 + .90 * strength) ** (1.0 + intensity)
    return weight


def equities(cards, board, opponents, discarded=(), exposed=(), dead_public=(), ranges=()):
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
    fixed = tuple(tuple(_CARD[c] for c in xs) for xs in exposed) if exposed else ((),) * opponents
    blocked = set(hole + community + dead + tuple(_CARD[c] for c in dead_public))
    for known in fixed: blocked.update(known)
    deck = [card for card in _DECK if card not in blocked]
    # Per-state deterministic sampling: reproducible across processes and no
    # mutable global RNG, caches, or information carried between tables.
    seed = 2166136261
    for card in sorted(set(cards) | set(board) | set(discarded)):
        seed = ((seed ^ (_INDEX[card] + 1)) * 16777619) & 0xFFFFFFFF
    seed ^= opponents * 104729
    sample = random.Random(seed).sample
    missing = 5 - len(community)
    draws = missing + sum(2 - len(k) for k in fixed)
    samples = 24 if opponents <= 3 else 16
    totals = [0.0] * len(hands)
    total_weight = 0.0
    for _ in range(samples):
        picked = sample(deck, draws)
        completed = community + tuple(picked[:missing])
        scores = []
        at = missing
        weight = 1.0
        for j, known in enumerate(fixed):
            need = 2 - len(known)
            enemy = known + tuple(picked[at:at + need]); at += need
            scores.append(_EVALUATE(completed + enemy))
            if ranges:
                weight *= _range_weight(enemy, ranges[j])
        total_weight += weight
        best = max(scores)
        for i, hand in enumerate(hands):
            value = _EVALUATE(completed + hand)
            if value > best:
                totals[i] += weight
            elif value == best:
                totals[i] += weight / (1 + scores.count(best))
    return tuple(value / total_weight for value in totals)


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


def choose_discard(cards, board, values):
    """Prefer current hand strength only when sampled equities tie exactly.

    Equity remains primary: a drawing hand can still beat a made hand on EV.
    Shared samples often give both trips and a full house 100% against weak
    sampled opponents; using index order for that tie throws away the full house.
    """
    hole = tuple(_CARD[card] for card in cards)
    community = tuple(_CARD[card] for card in board)
    pairs = ((hole[1], hole[2]), (hole[0], hole[2]), (hole[0], hole[1]))
    return max(range(3), key=lambda index: (values[index], _EVALUATE(community + pairs[index])))


def decide(state: GameState) -> Action:
    live = [seat for seat in state.seats if seat.seat != state.seat and seat.status in ("active", "all_in")]
    if state.phase not in ("select", "betting"):
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)

    values = equities(state.cards, state.board, len(live), state.variant.get("discarded", ()), tuple(tuple(s.shown_cards) for s in live), tuple(c for s in state.seats for c in s.shown_cards), opponent_ranges(state, live))
    if state.phase == "select":
        discard = choose_discard(state.cards, state.board, values)
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
