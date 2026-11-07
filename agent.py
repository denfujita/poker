"""A small equity / pot-odds baseline for the Bay Area discard-and-reveal variant.

This is a chip-EV heuristic, not a GTO or ICM solver. Opponent exposed cards are fixed; unknown cards are sampled without replacement.
Folded public cards and our discard are removed. Public actions and bet sizes weight opponent hand hypotheses. This is a
value-heavy heuristic with a nonzero bluff likelihood, not a calibrated solver.
All game-dependent work is local to a decision; no cross-table state is kept.
"""

import json
import os
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

# Preflop policy (research/analysis/export_policy.py): per-combo [percentile, bucket] of true 3-card
# heads-up equity (0 = best) plus the full chip-EV jam/fold solver policy by bucket. Loaded once at import.
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "preflop_policy.json")) as _f:
    _POLICY = json.load(_f)
_COMBO, _JAM, _CALL = _POLICY["combo"], _POLICY["jam"], _POLICY["call"]
_SOLVED_STACKS = (3, 5, 7, 10, 12, 15, 20)
_SOLVED_SIZES = (2, 3, 4, 6, 8)
_BEHIND_NAME = {1: "SB", 2: "BTN", 3: "CO", 4: "HJ", 5: "LJ", 6: "UTG+1", 7: "UTG"}
# AZ-style first-in raise thresholds (share of 3-card hands, by position) for stacks above the jam/fold zone.
_OPEN = {"SB": .70, "BTN": .65, "CO": .34, "HJ": .26}
_OPEN_EARLY = .17
# Facing one non-all-in raise: (re-raise below, call below) percentile thresholds by our position.
_VS_RAISE = {"BB": (.08, .30), "SB": (.06, .20)}
_VS_RAISE_OTHER = (.05, .10)
JAM_ZONE_BB = 15


def _nearest(value, options):
    return min(options, key=lambda option: (abs(option - value), -option))


def _preflop(state, hero):
    """AZ-style preflop: jam/fold policy at <= 15 bb, fixed-size opens above, tight vs raises.

    Returns an Action, or None to fall back to the equity logic for states this does not cover.
    """
    entry = _COMBO.get("".join(sorted(state.cards)))
    if entry is None or len(state.cards) != 3:
        return None
    pct, bucket = entry
    bb = max(1, state.blinds.big_blind)
    raise_ = state.can("raise")
    check = state.can("check")
    call = state.can("call")
    passive = Action.check() if check else Action.fold() if state.can("fold") else None
    if passive is None:
        return None

    dealt = [s for s in state.seats if s.status != "busted"]
    others = [s for s in state.seats if s.seat != state.seat and s.status in ("active", "all_in")]
    acted = {e.seat for e in state.history if e.kind in ("fold", "check", "call", "raise") and e.seat != state.seat}
    behind = [s for s in others if s.seat not in acted and s.status == "active"]
    blinds = [e.seat for e in state.history if e.kind == "blind"]
    raises = [e for e in state.history if e.kind == "raise"]
    n = _nearest(len(dealt), _SOLVED_SIZES)
    me_total = hero.stack + hero.bet

    def jam():
        return Action.raise_to(int(raise_.max_amount)) if raise_ else (Action.call() if call else passive)

    def raise_to(total):
        if not raise_:
            return Action.call() if call else passive
        total = int(min(raise_.max_amount, max(raise_.min_amount, total)))
        return jam() if total - hero.bet >= .4 * me_total else Action.raise_to(total)

    def my_name():
        if len(blinds) >= 2 and state.seat == blinds[1]:
            return "BB"
        if blinds and state.seat == blinds[0]:
            return "SB"
        return _BEHIND_NAME.get(min(7, len(dealt) - 1 - len(acted)), "UTG")

    if not raises:
        if not behind:  # big blind with the option: raise the very top, else check
            if pct < .15 and raise_:
                limpers = sum(1 for e in state.history if e.kind == "call")
                eff = min(me_total, max((s.stack + s.bet for s in others), default=0)) / bb
                return jam() if eff <= JAM_ZONE_BB else raise_to(int((3 + limpers) * bb))
            return passive
        eff = min(me_total, max(s.stack + s.bet for s in behind)) / bb
        pos = _BEHIND_NAME.get(min(len(behind), n - 1), "UTG")
        if eff <= JAM_ZONE_BB:
            policy = _JAM.get(str(n), {}).get(pos)
            if policy is None:
                return None
            return jam() if policy[str(_nearest(eff, _SOLVED_STACKS))][bucket] >= .5 else passive
        if pct < _OPEN.get(pos, _OPEN_EARLY):
            limpers = sum(1 for e in state.history if e.kind == "call")
            return raise_to(int(2.5 * bb + limpers * bb))
        return passive

    last = raises[-1]
    raiser = next((s for s in state.seats if s.seat == last.seat), None)
    cost = min(max(0, state.to_call), hero.stack)
    big = cost >= .4 * me_total or (raiser is not None and raiser.status == "all_in")
    eff = min(me_total, (raiser.stack + raiser.bet) if raiser else me_total) / bb
    if len(raises) == 1 and big:
        # Facing an open jam: the solver's call policy for (jammer position, our position, depth).
        before = set()
        for e in state.history:
            if e is last:
                break
            if e.kind in ("fold", "check", "call", "raise"):
                before.add(e.seat)
        jpos = _BEHIND_NAME.get(min(n - 1, len(dealt) - 1 - len(before)), "UTG")
        table = _CALL.get(str(n), {}).get(jpos, {}).get(str(_nearest(eff, _SOLVED_STACKS)), {})
        policy = table.get(my_name())
        if policy is not None and eff <= 20:
            want = policy[bucket] >= .5
        else:  # deeper or uncovered: AZ-like tight all-in calls, wider with a great price
            price = cost / max(1, state.pot + cost)
            want = pct < (.35 if price <= .3 else .10)
        return (Action.call() if call else passive) if want else passive
    if big:
        return (Action.call() if call else passive) if pct < .04 else passive
    if len(raises) >= 2:
        if pct < .03:
            return jam()
        return Action.call() if call and pct < .06 else passive
    three, flat = _VS_RAISE.get(my_name(), _VS_RAISE_OTHER)
    if pct < three:
        return jam() if eff <= 25 else raise_to(3 * last.amount)
    if pct < flat and call:
        return Action.call()
    return passive


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

    if state.phase == "betting" and not state.board:
        try:
            hero = next(seat for seat in state.seats if seat.seat == state.seat)
            chosen = _preflop(state, hero)
        except Exception:  # any gap in the preflop tables falls back to the equity logic below
            chosen = None
        if chosen is not None:
            return chosen

    values = equities(state.cards, state.board, len(live), state.variant.get("discarded", ()), tuple(tuple(s.shown_cards) for s in live), tuple(c for s in state.seats for c in s.shown_cards), opponent_ranges(state, live))
    if state.phase == "select":
        discard = choose_discard(state.cards, state.board, values)
        retained = [index for index in range(3) if index != discard]
        # Revealing either retained card has identical showdown equity. Like the top teams, expose the
        # card that connects less with the board (pairs it / shares its suits less), then the lower rank.
        board_ranks = [card[0] for card in state.board]
        board_suits = [card[1] for card in state.board]
        reveal = min(retained, key=lambda index: (state.cards[index][0] in board_ranks,
                                                  board_suits.count(state.cards[index][1]),
                                                  _INDEX[state.cards[index]]))
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
        # One two-thirds-pot value size (AZ-style), expressed as TOTAL street commitment.
        target = hero.bet + cost + max(1, 2 * (state.pot + cost) // 3)
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
