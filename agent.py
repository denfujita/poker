"""A tighter context-aware heuristic for the Bay Area discard-and-reveal variant.

Yifan v7 proposes actions; terminal heads-up calls additionally respect expected tournament points. This is not a solved strategy. Opponent exposed cards are fixed; unknown cards are sampled without replacement.
Folded public cards and our discard are removed. Public actions and bet sizes weight opponent hand hypotheses. This is a
value-heavy heuristic with a nonzero bluff likelihood, not a calibrated solver.
All game-dependent work is local to a decision; no cross-table state is kept.
"""

import json
import os
import random
from bisect import bisect_left, bisect_right
from point_value import prepare_point_value, prepare_settlement

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

# Reviewed teammate asset: sampled three-card heads-up strength ORDERING only.
# Neither these percentiles nor the thresholds below are a solved GTO policy.
# Full jam/call mixtures are used only in the restricted blind-versus-blind
# domain below. They remain chip-EV policies for an approximate selection model.
with open(os.path.join(os.path.dirname(__file__), "preflop_policy.json")) as _policy_file:
    _PREFLOP_POLICY = json.load(_policy_file)
    _PREFLOP_COMBOS = _PREFLOP_POLICY["combo"]


def supported_jamfold_spot(state):
    """Identify an exact supported SB/BB chip-EV spot, or keep the v4 policy.

    The exported game has equal stacks, 0.5/1 blinds, no antes, and no overcalls.
    Restricting it to the two blinds after all other seats fold avoids the
    missing overcall model. Exact depths avoid interpolating unrelated charts.
    The selection model and equity buckets are still approximations, not a
    solution to the full discard/reveal tournament or its ICM objective.
    """
    if state.phase != "betting" or state.board or len(state.cards) != 3:
        return None
    blinds = state.blinds
    if blinds.ante or blinds.small_blind <= 0 or 2 * blinds.small_blind != blinds.big_blind:
        return None
    alive = sorted(s.seat for s in state.seats if s.status != "busted")
    n = len(alive)
    if n not in (2, 3, 4, 6, 8) or state.button not in alive:
        return None
    after = [s for s in alive if s > state.button] + [s for s in alive if s <= state.button]
    sb, bb = (state.button, after[0]) if n == 2 else (after[0], after[1])
    if state.seat not in (sb, bb):
        return None
    seats = {s.seat: s for s in state.seats}
    if any(s.status != "folded" or s.bet for s in state.seats if s.seat in alive and s.seat not in (sb, bb)):
        return None
    # Folded nonblinds contribute nothing and cannot overcall; their remaining
    # stack sizes are irrelevant to this restricted chip-EV pot.
    totals = [seats[i].stack + seats[i].bet for i in (sb, bb)]
    if min(totals) != max(totals):
        return None
    total = totals[0]
    depth, remainder = divmod(total, blinds.big_blind)
    if remainder or depth not in (3, 5, 7, 10, 12, 15, 20):
        return None
    # Demand the actual two blind posts, with no extra dead chips or previous
    # voluntary action. Current history is the authoritative event stream.
    posts, raises, folded = {}, [], set()
    for event in state.history:
        if event.kind == "blind":
            if event.seat in posts:
                return None
            posts[event.seat] = event.amount
        elif event.kind == "fold":
            if raises or event.seat in (sb, bb):
                return None
            folded.add(event.seat)
        elif event.kind == "raise":
            raises.append(event)
        elif event.kind not in ("hand", "prize_the_shover"):
            return None
    if posts != {sb: blinds.small_blind, bb: blinds.big_blind}:
        return None
    if folded != set(alive) - {sb, bb}:
        return None
    entry = _PREFLOP_COMBOS.get("".join(sorted(state.cards)))
    if entry is None:
        return None
    bucket = entry[1]
    if state.seat == sb and not raises:
        legal = state.can("raise")
        if (seats[sb].status != "active" or seats[bb].status != "active"
                or seats[sb].bet != blinds.small_blind or seats[bb].bet != blinds.big_blind
                or state.pot != blinds.small_blind + blinds.big_blind
                or state.to_call != blinds.big_blind - blinds.small_blind
                or not legal or legal.max_amount != total
                or not (legal.min_amount <= total <= legal.max_amount)):
            return None
        vector = _PREFLOP_POLICY.get("jam", {}).get(str(n), {}).get("SB", {}).get(str(depth))
        action = Action.raise_to(total)
        kind = "jam"
    elif state.seat == bb and len(raises) == 1:
        event = raises[0]
        if (event.seat != sb or event.amount != total
                or seats[sb].status != "all_in" or seats[sb].stack != 0 or seats[sb].bet != total
                or seats[bb].status != "active" or seats[bb].bet != blinds.big_blind
                or state.pot != total + blinds.big_blind
                or state.to_call != total - blinds.big_blind or not state.can("call")):
            return None
        vector = _PREFLOP_POLICY.get("call", {}).get(str(n), {}).get("SB", {}).get(str(depth), {}).get("BB")
        action = Action.call()
        kind = "call"
    else:
        return None
    if vector is None or not isinstance(bucket, int) or not 0 <= bucket < len(vector):
        return None
    probability = vector[bucket]
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        return None
    return action, probability, kind, n, depth


def supported_jamfold_action(state):
    spot = supported_jamfold_spot(state)
    if spot is None:
        return None
    action, probability, kind, players, depth = spot
    # A local seeded generator preserves fractional bucket probabilities without
    # storing state or drawing from another table's random-number stream.
    seed = (f"jamfold-v1:{state.config.table_id}:{state.hand_number}:{state.seat}:"
            f"{players}:{depth}:{kind}:{''.join(sorted(state.cards))}")
    if probability == 1 or (probability > 0 and random.Random(seed).random() < probability):
        return action
    # A chart fold is terminal; never fall through to v4's equity/value branches.
    return _preflop_passive(state)

# ---- Exploit knobs from scored rounds 2-3: our BB folds 67% to late opens and re-raises 2% (top teams
# re-raise 29-46%, mostly all-in); we c-bet 63% (top 77-91%). RESHOVE_PCT = 0 and SMALL_CBET = False give v6.
RESHOVE_PCT = .09         # SB/BB vs one unlimped CO/BTN/SB open: shove this top share of hands [0 = off]
RESHOVE_MIN_BB = 12       # ...only when the raiser's effective stack is in this window (bb)
RESHOVE_MAX_BB = 25
SMALL_CBET = True         # heads-up flop, we made the last preflop raise, checked to: bet small [False]
SMALL_CBET_FRAC = .33     # share of the pot
SMALL_CBET_MARGIN = .02   # bet when (margin-adjusted) equity >= 1/2 - this


def preflop_context(state):
    alive = sorted(s.seat for s in state.seats if s.status != "busted")
    if state.seat not in alive or len(alive) < 2:
        return None
    # Seat numbers preserve clockwise table order, even with busted holes.
    after = [s for s in alive if s > state.button] + [s for s in alive if s <= state.button]
    if state.button in alive:
        after.remove(state.button)
        after.append(state.button)
    n = len(alive)
    if n == 2:
        button = state.button if state.button in alive else after[-1]
        order = [button, next(s for s in alive if s != button)]
        names = ("SB", "BB")
    else:
        order = after[2:] + after[:2]
        prefixes = {3: (), 4: (), 5: ("HJ",), 6: ("LJ", "HJ"),
                    7: ("UTG", "LJ", "HJ"),
                    8: ("UTG", "UTG1", "LJ", "HJ"),
                    9: ("UTG", "UTG1", "UTG2", "LJ", "HJ"),
                    10: ("UTG", "UTG1", "UTG2", "UTG3", "LJ", "HJ")}
        names = ("BTN", "SB", "BB") if n == 3 else prefixes[n] + ("CO", "BTN", "SB", "BB")
    by_id = {s.seat: s for s in state.seats}
    hero = by_id[state.seat]
    live = [s for s in state.seats if s.seat != state.seat and s.status in ("active", "all_in")]
    bb = max(1, state.blinds.big_blind)
    raises = []
    limpers = set()
    for event in state.history:
        if event.kind == "board":
            break
        if event.kind == "raise":
            raises.append(event.seat)
        elif event.kind == "call" and not raises and event.seat != state.seat:
            limpers.add(event.seat)
    max_bet = max(s.bet for s in state.seats)
    last_raiser = by_id.get(raises[-1]) if raises else None
    all_in = bool(last_raiser and last_raiser.status == "all_in" and last_raiser.bet >= max_bet)
    pot_class = "all_in" if all_in else "raised" if raises else "limped" if limpers else "unopened"
    hero_total = hero.stack + hero.bet
    cover = max((s.stack + s.bet for s in live), default=hero_total)
    effective = min(hero_total, cover)
    facing_depth = min(hero_total, last_raiser.stack + last_raiser.bet) if last_raiser else effective
    return {"position": names[order.index(state.seat)], "players": n,
            "bb": bb, "effective_bb": effective / bb, "facing_bb": facing_depth / bb,
            "hero": hero, "live": live, "pot_class": pot_class,
            "raise_count": len(raises), "limpers": len(limpers),
            "max_bet": max_bet, "cover": cover,
            "last_raiser_position": names[order.index(last_raiser.seat)] if last_raiser else None}


def _preflop_passive(state):
    if state.can("check"):
        return Action.check()
    if state.can("fold"):
        return Action.fold()
    first = state.legal_actions[0]
    return Action(first.kind, first.min_amount)


def _preflop_raise(state, target):
    legal = state.can("raise")
    if not legal:
        return None
    return Action.raise_to(int(min(legal.max_amount, max(legal.min_amount, target))))


def preflop_reraise_allowed(context, percentile):
    depth = context["facing_bb"]
    limit = .025 if depth > 20 else .045 if depth > 10 else .085
    if context["raise_count"] >= 2:
        limit *= .55
    return percentile <= limit


def preflop_action(state, percentile, equity=None, call_pot=None):
    """Complete policy with weighted equity+eligible call pot; else gated fallback.

    Returns None outside preflop or for a qualified defensive hand whose equity
    has not been supplied. Integrators should pass their simulated pot-share
    equity and side-pot-aware eligible post-call pot, not the ordinal percentile.
    """
    if state.phase != "betting" or state.board or percentile is None:
        return None
    ctx = preflop_context(state)
    if ctx is None:
        return None
    hero, bb = ctx["hero"], ctx["bb"]
    pos, depth, kind = ctx["position"], ctx["effective_bb"], ctx["pot_class"]
    cost = min(hero.stack, max(0, state.to_call))
    if kind in ("unopened", "limped"):
        if cost and state.can("call") and not state.can("raise"):
            # A short all-in blind can leave only a cheap call/fold choice.
            # Do not reinterpret inability to raise as a reason to fold.
            if equity is None or call_pot is None:
                return None
            return Action.call() if equity >= cost / max(1, call_pot) + .015 else _preflop_passive(state)
        opening = {"UTG": .17, "UTG1": .19, "UTG2": .19, "UTG3": .19,
                   "LJ": .22, "HJ": .26, "CO": .34, "BTN": .60, "SB": .62, "BB": .30}[pos]
        if ctx["players"] == 2:
            opening = .82 if pos == "SB" else .42
        if kind == "limped":
            opening = max(.10, opening - .08 - .025 * max(0, ctx["limpers"] - 1))
        if depth <= 5:
            opening = min(.92, opening + .20)
        elif depth <= 10:
            opening = min(.85, opening + .10)
        if percentile > opening:
            return _preflop_passive(state)
        if depth <= 10:
            target = min(hero.stack + hero.bet, ctx["cover"])
        else:
            # Normal opens are TOTAL street commitments, not extra chips.
            size = 2.2 if depth <= 35 else 2.5
            target = round((size + ctx["limpers"]) * bb)
        return _preflop_raise(state, target) or (None if cost else _preflop_passive(state))

    # Blind re-shove vs a late steal (no limpers, one raise): fold equity, no postflop play.
    if (RESHOVE_PCT and kind == "raised" and ctx["raise_count"] == 1 and ctx["limpers"] == 0
            and pos in ("SB", "BB") and ctx["last_raiser_position"] in ("CO", "BTN", "SB")
            and RESHOVE_MIN_BB <= ctx["facing_bb"] <= RESHOVE_MAX_BB and percentile <= RESHOVE_PCT):
        shove = _preflop_raise(state, hero.stack + hero.bet)
        if shove:
            return shove

    # Raised/all-in pots: ordinal gate first, then actual equity and call price.
    facing = ctx["facing_bb"]
    if kind == "all_in":
        limit = .06 if facing > 20 else .14 if facing > 10 else .34 if facing > 5 else .50
    else:
        limit = .34 if pos == "BB" else .18 if pos == "SB" else .12
        if ctx["players"] == 2:
            limit = max(limit, .42)
        if ctx["raise_count"] >= 2:
            limit = min(limit, .07 if pos in ("SB", "BB") else .04)
        if cost > 8 * bb:
            limit = min(limit, .07)
    price = cost / max(1, state.pot + cost)
    cheap = cost <= bb and price <= .08
    if percentile > limit and not cheap:
        return _preflop_passive(state)
    if not cost:
        return _preflop_passive(state)
    if equity is None or call_pot is None:
        return None
    premium = .06 + min(.08, .04 * max(0, ctx["raise_count"] - 1))
    if cost >= .25 * max(1, hero.stack):
        premium += .04
    if kind == "all_in" or cost > 8 * bb:
        premium += .03
    if facing <= 10:
        premium *= .5
    if ctx["players"] == 2:
        premium *= .75
    required = cost / max(1, call_pot) + min(.20, premium)
    if equity < required:
        return _preflop_passive(state)
    if preflop_reraise_allowed(ctx, percentile):
        fair = 1.0 / (len(ctx["live"]) + 1)
        if equity >= min(.85, fair + .22):
            target = min(hero.stack + hero.bet, ctx["cover"]) if facing <= 15 else 3 * ctx["max_bet"]
            action = _preflop_raise(state, target)
            if action:
                return action
    return Action.call() if state.can("call") else _preflop_passive(state)



def choose_reveal(cards, board, retained):
    """Hide the card most connected to the flop; this is an information heuristic."""
    ranks = tuple(card[0] for card in board)
    suits = tuple(card[1] for card in board)
    return min(retained, key=lambda index: (
        ranks.count(cards[index][0]),
        max(0, suits.count(cards[index][1]) - 1),
        _INDEX[cards[index]] // 4,
        _INDEX[cards[index]] % 4,
    ))


def postflop_context(state, live):
    """Read only this hand's public action sequence, retaining street boundaries."""
    live_ids = {seat.seat for seat in live}
    street = 0
    pot = 0
    bets = {}
    last_by_street = {}
    opponent_raises = 0
    hero_raised = False
    last_ratio = 0.0
    for event in state.history:
        kind, seat, amount = event.kind, event.seat, event.amount
        if kind == "board":
            street += len(event.cards)
            bets = {}
            opponent_raises = 0
            hero_raised = False
            last_ratio = 0.0
        elif kind in ("ante", "blind", "call", "raise"):
            added = max(0, amount - bets.get(seat, 0)) if kind == "raise" else amount
            if kind == "raise":
                last_by_street[street] = seat
                if seat == state.seat:
                    hero_raised = True
                elif seat in live_ids:
                    opponent_raises += 1
                    last_ratio = added / max(1, pot)
            pot += added
            if kind != "ante":
                bets[seat] = bets.get(seat, 0) + added
    aggressor = last_by_street.get(len(state.board))
    barrels = 1 if aggressor in live_ids else 0
    if len(state.board) >= 4 and last_by_street.get(len(state.board) - 1) == aggressor:
        barrels += 1
        if len(state.board) == 5 and last_by_street.get(3) == aggressor:
            barrels += 1
    # Position among players who can still bet; an all-in player has no later turn.
    seats = len(state.seats)
    order = lambda seat: ((seat - state.button - 1) % seats)
    in_position = all(order(state.seat) > order(seat.seat)
                      for seat in live if seat.status == "active")
    cbet = (len(state.board) == 3 and opponent_raises == 1 and not hero_raised
            and aggressor == last_by_street.get(0))
    return opponent_raises, hero_raised, last_ratio, barrels, in_position, cbet


def made_value_level(cards, board):
    """Separate a private made hand from two pair/trips supplied by the board."""
    hole = tuple(_CARD[card] for card in cards)
    community = tuple(_CARD[card] for card in board)
    score = _EVALUATE(community + hole)
    category = score >> 24
    if len(board) == 5 and score == _EVALUATE(community):
        return 0
    if category >= 4:
        return category
    ranks = [card.rank for card in community]
    private = [card.rank for card in hole]
    involved_pairs = {rank for rank in private if ranks.count(rank) + private.count(rank) >= 2}
    if category == 3:
        return 3 if any(ranks.count(rank) + private.count(rank) >= 3 for rank in private) else 0
    if category == 2:
        return 2 if len(involved_pairs) >= 2 else 1 if involved_pairs else 0
    return 1 if involved_pairs else 0


def defense_premium(state, hero, live, cost, context, value_level, raw_equity):
    """Extra caution only for large/repeated pressure, not blanket postflop folding."""
    if not cost:
        return 0.0
    raises, hero_raised, ratio, barrels, in_position, cbet = context
    reraised = raises >= 2 or (hero_raised and raises > 0)
    large = ratio >= .75
    repeated_barrel = barrels >= 2 and (ratio >= .5 or cost >= .25 * hero.stack)
    if not (reraised or large or repeated_barrel):
        return 0.0
    if value_level >= 4 and raw_equity >= .97:
        return 0.0
    premium = (.035 if reraised else 0.0) + (.025 if large else 0.0)
    premium += .025 if ratio >= 1.5 else 0.0
    premium += .015 * max(0, barrels - 1) if repeated_barrel else 0.0
    premium += .015 * min(3, len(live) - 1)
    premium += .01 if not in_position else 0.0
    premium += .015 if len(state.board) == 5 else 0.0
    # Preserve cheap/committed short-stack continuations; no blanket jam rule.
    bb = max(1, state.blinds.big_blind)
    cover = max((seat.stack + seat.bet for seat in live), default=0)
    effective_bb = min(hero.stack + hero.bet, cover) / bb
    if effective_bb <= 10 or hero.stack <= state.pot / 2:
        premium *= .35
    if value_level >= 3 and raw_equity >= .9:
        premium *= .25
    if cbet and len(live) == 1 and ratio <= .8:
        premium *= .8
    return premium


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


def exact_river_groups(hole, community, fixed, deck, ranges, groups):
    """Exact existing-model shares for two single-hidden-card river opponents.

    Opponent likelihoods factor by hand. The only dependence is that their
    hidden cards cannot coincide. Products of weight sums, minus same-card
    collisions, integrate every ordered pair in linear rather than quadratic
    work. All groups use this one joint posterior, including excluded players.
    """
    hero = _EVALUATE(community + hole)
    records = []
    buckets = []
    for j in range(2):
        values = []
        sums = [0.0, 0.0, 0.0]  # Below hero, tied with hero, above hero.
        contexts = ranges[j] if ranges else ()
        for card in deck:
            hand = fixed[j] + (card,)
            score = _EVALUATE(community + hand)
            category = 0 if score < hero else 1 if score == hero else 2
            weight = _range_weight(hand, contexts) if contexts else 1.0
            values.append((weight, category))
            sums[category] += weight
        records.append(values)
        buckets.append(sums)
    first, second = buckets
    w0, w1 = sum(first), sum(second)
    normalizer = w0 * w1
    full = first[0] * second[0] + .5 * (first[1] * second[0] + first[0] * second[1])
    full += first[1] * second[1] / 3.0
    single0 = single1 = 0.0
    for (a, ca), (b, cb) in zip(*records):
        collision = a * b
        normalizer -= collision
        if ca < 2 and cb < 2:
            full -= collision / (1 + (ca == 1) + (cb == 1))
        if ca < 2:
            single0 += a * (w1 - b) / (1 + (ca == 1))
        if cb < 2:
            single1 += b * (w0 - a) / (1 + (cb == 1))
    if normalizer <= 0:
        return None
    values = {(): 1.0, (0,): single0 / normalizer, (1,): single1 / normalizer,
              (0, 1): full / normalizer, (1, 0): full / normalizer}
    return tuple((min(1.0, max(0.0, values[group])),) for group in groups)


def equities(cards, board, opponents, discarded=(), exposed=(), dead_public=(), ranges=(),
             contender_groups=None):
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
        result = (1.0,) * len(hands)
        return result if contender_groups is None else tuple(result for _ in contender_groups)
    fixed = tuple(tuple(_CARD[c] for c in xs) for xs in exposed) if exposed else ((),) * opponents
    blocked = set(hole + community + dead + tuple(_CARD[c] for c in dead_public))
    for known in fixed: blocked.update(known)
    deck = [card for card in _DECK if card not in blocked]
    if len(hole) == 2 and len(community) == 5 and opponents == 1 and len(fixed[0]) == 1:
        # With one exposed card, enumerate the remaining hidden card exactly.
        # The likelihood model is unchanged; this removes 24-sample variance.
        hero_score = _EVALUATE(community + hole)
        total_weight = weighted_share = 0.0
        for card in deck:
            enemy = fixed[0] + (card,)
            weight = _range_weight(enemy, ranges[0]) if ranges else 1.0
            enemy_score = _EVALUATE(community + enemy)
            total_weight += weight
            if hero_score > enemy_score:
                weighted_share += weight
            elif hero_score == enemy_score:
                weighted_share += .5 * weight
        if total_weight > 0:
            result = (weighted_share / total_weight,)
            return (result if contender_groups is None else
                    tuple(result if group else (1.0,) for group in contender_groups))
    if (contender_groups is not None and len(hole) == 2 and len(community) == 5
            and opponents == 2 and all(len(known) == 1 for known in fixed)
            and any(len(group) < opponents for group in contender_groups)):
        exact = exact_river_groups(hole, community, fixed, deck, ranges, contender_groups)
        if exact is not None:
            return exact
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
    grouped = [[0.0] * len(hands) for _ in contender_groups] if contender_groups is not None else None
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
        if grouped is not None:
            contests = []
            for group in contender_groups:
                relevant = [scores[j] for j in group]
                best = max(relevant, default=-1)
                contests.append((best, relevant.count(best)))
            for i, hand in enumerate(hands):
                value = _EVALUATE(completed + hand)
                for g, (best, ties) in enumerate(contests):
                    if value > best:
                        grouped[g][i] += weight
                    elif value == best:
                        grouped[g][i] += weight / (1 + ties)
            continue
        best = max(scores)
        for i, hand in enumerate(hands):
            value = _EVALUATE(completed + hand)
            if value > best:
                totals[i] += weight
            elif value == best:
                totals[i] += weight / (1 + scores.count(best))
    if grouped is not None:
        return tuple(tuple(value / total_weight for value in group) for group in grouped)
    return tuple(value / total_weight for value in totals)


def contributions(state):
    """Reconstruct per-hand commitments; raise events contain STREET totals."""
    total = {seat.seat: 0 for seat in state.seats}
    street = {seat.seat: 0 for seat in state.seats}
    antes = {}
    for event in state.history:
        if event.kind == "board":
            # Completed streets refund a unique unmatched high bet silently.
            # Antes are absent from street totals and are never refunded here.
            ordered = sorted(street.items(), key=lambda item: item[1], reverse=True)
            if len(ordered) > 1:
                total[ordered[0][0]] -= ordered[0][1] - ordered[1][1]
            street = dict.fromkeys(street, 0)
        elif event.seat in total:
            seat = event.seat
            if event.kind == "ante":
                total[seat] += event.amount
                antes[seat] = antes.get(seat, 0) + event.amount
            elif event.kind in ("blind", "call"):
                total[seat] += event.amount
                street[seat] += event.amount
            elif event.kind == "raise":
                added = max(0, event.amount - street[seat])
                total[seat] += added
                street[seat] = event.amount
    # The engine also trims unmatched antes before any blinds are posted.
    if len(antes) > 1:
        ordered = sorted(antes.items(), key=lambda item: item[1], reverse=True)
        total[ordered[0][0]] -= ordered[0][1] - ordered[1][1]
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


def pot_layers(state, committed, hero_cost, live, additions=None):
    """Amounts and eligible opponent indexes for hero's post-action pots.

    Folded commitments remain dead money. An all-in player's eligibility ends
    at its contribution. An active opponent can still respond, so retain it up
    to its available stack without crediting any unmade call to the call pot.
    This preserves the ordinary single-pot assumption while separating capped
    opponents. Projected raises explicitly supply their assumed caller additions.
    """
    additions = additions or {}
    after = {seat: amount + additions.get(seat, 0) for seat, amount in committed.items()}
    after[state.seat] += hero_cost
    cap = after[state.seat]
    capacities = tuple(committed[seat.seat] + seat.stack
                       if seat.status == "active" else after[seat.seat] for seat in live)
    levels = sorted({min(cap, amount) for amount in (*after.values(), *capacities) if amount > 0})
    remaining = eligible_pot(state, committed, hero_cost, additions)
    result = {}
    previous = 0
    for level in levels:
        amount = min(remaining, (level - previous) * sum(value >= level for value in after.values()))
        previous = level
        if amount <= 0:
            continue
        group = tuple(j for j, capacity in enumerate(capacities) if capacity >= level)
        result[group] = result.get(group, 0) + amount
        remaining -= amount
    return tuple((amount, group) for group, amount in result.items())


def layer_payout(layers, shares, hand=0, margin=0.0):
    """Expected chips, splitting ties within each layer's eligible field.

    Uncontested money, including an unmatched return, is certain. It receives
    no equity margin, so paying and recovering an uncalled excess cancels out.
    """
    return sum(amount * (max(0.0, shares[group][hand] - margin) if group else 1.0)
               for amount, group in layers)


def raise_projection(state, hero, live, cost, preflop=False):
    """The existing deterministic raise size, before any equity comparison."""
    legal = state.can("raise")
    callers = [seat for seat in live if seat.status == "active" and seat.stack > 0]
    if not legal or not callers:
        return None
    if preflop:
        ctx = preflop_context(state)
        if ctx is None:
            return None
        target = min(hero.stack + hero.bet, ctx["cover"]) if ctx["facing_bb"] <= 15 else 3 * ctx["max_bet"]
        target = int(min(legal.max_amount, max(legal.min_amount, target)))
    else:
        target = max(seat.bet for seat in state.seats) + max(1, 62 * (state.pot + cost) // 100)
        cover = max(seat.bet + seat.stack for seat in callers)
        target = int(min(legal.max_amount, cover, max(legal.min_amount, target)))
    if target < legal.min_amount:
        return None
    additions = {seat.seat: min(seat.stack, max(0, target - seat.bet)) for seat in callers}
    return target, target - hero.bet, additions


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


def decide_v7(state: GameState) -> Action:
    live = [seat for seat in state.seats if seat.seat != state.seat and seat.status in ("active", "all_in")]
    if state.phase not in ("select", "betting"):
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)

    hero = next(seat for seat in state.seats if seat.seat == state.seat)
    preflop = state.phase == "betting" and not state.board
    percentile = None
    if preflop:
        chosen = supported_jamfold_action(state)
        if chosen is not None:
            return chosen
        entry = _PREFLOP_COMBOS.get("".join(sorted(state.cards)))
        percentile = entry[0] if entry is not None else None
        chosen = preflop_action(state, percentile)
        if chosen is not None:
            return chosen

    check = state.can("check")
    call = state.can("call")
    cost = min(max(0, state.to_call), hero.stack) if call else 0
    committed = contributions(state)
    call_pot = eligible_pot(state, committed, cost)
    call_layers = pot_layers(state, committed, cost, live)
    projection = raise_projection(state, hero, live, cost, preflop) if state.phase == "betting" else None
    raise_layers = pot_layers(state, committed, projection[1], live, projection[2]) if projection else ()
    full_group = tuple(range(len(live)))
    groups = tuple(dict.fromkeys((full_group, *(group for _, group in call_layers + raise_layers))))
    args = (state.cards, state.board, len(live), state.variant.get("discarded", ()),
            tuple(tuple(s.shown_cards) for s in live),
            tuple(c for s in state.seats for c in s.shown_cards), opponent_ranges(state, live))
    if groups == (full_group,):
        shares = {full_group: equities(*args)}
    else:
        shares = dict(zip(groups, equities(*args, contender_groups=groups)))
    single_pot = all(group == full_group for _, group in call_layers)
    values = shares[full_group] if single_pot or not call_pot else tuple(
        layer_payout(call_layers, shares, hand=i) / call_pot for i in range(len(shares[full_group])))
    if state.phase == "select":
        discard = choose_discard(state.cards, state.board, values)
        retained = [index for index in range(3) if index != discard]
        reveal = choose_reveal(state.cards, state.board, retained)
        return Action("select", cards=(discard, reveal))

    raw_equity = max(values)
    hand_index = max(range(len(values)), key=values.__getitem__)
    if preflop:
        # Defensive decisions are terminal: a rejected call cannot fall through
        # to the generic value-raise branch and become a weak reraise.
        action = preflop_action(state, percentile, equity=raw_equity, call_pot=call_pot) or _preflop_passive(state)
        if (action.kind == "raise" and projection and
                any(group != full_group for _, group in call_layers + raise_layers)):
            # A call-price equity cannot price a different projected side pot.
            # Keep the existing ordinal/value gate, then compare actual layers.
            raise_ev = layer_payout(raise_layers, shares, hand_index, .06) - projection[1]
            call_ev = layer_payout(call_layers, shares, hand_index, .06) - cost
            if raise_ev <= max(0.0, call_ev) + .05 * projection[1]:
                return Action.call() if call and call_ev >= 0 else _preflop_passive(state)
        return action
    context = postflop_context(state, live)
    value_level = made_value_level(state.cards, state.board)
    margin = pressure_margin(state, {seat.seat for seat in live}, cost)
    margin += defense_premium(state, hero, live, cost, context, value_level, raw_equity)
    equity = max(0.0, raw_equity - margin)
    passive_ev = (equity * call_pot if single_pot else
                  layer_payout(call_layers, shares, hand_index, margin)) - cost
    passive = Action.check() if check else Action.call() if call and passive_ev >= 0 else Action.fold()

    # Preserve first-in value bets. Facing resistance, require a private made
    # hand stronger than one pair unless genuinely short/committed and very strong.
    short_committed = hero.stack <= state.pot and raw_equity >= .85
    reraise_ok = (not cost or (passive.kind == "call" and
                  (value_level >= 2 or short_committed)))
    if projection and reraise_ok:
        target, raise_cost, additions = projection
        raise_pot = eligible_pot(state, committed, raise_cost, additions)
        # All active opponents are projected to continue; no fold equity.
        if all(group == full_group for _, group in raise_layers):
            value_equity = max(0.0, equity - (0.06 if cost else 0.025))
            raise_ev = value_equity * raise_pot - raise_cost
            fair_share = 1.0 / (len(live) + 1)
        else:
            payout = layer_payout(raise_layers, shares, hand_index, margin + (0.06 if cost else .025))
            raise_ev = payout - raise_cost
            certain = sum(amount for amount, group in raise_layers if not group)
            contested = max(1, raise_pot - certain)
            value_equity = max(0.0, payout - certain) / contested
            fair_share = sum(amount / (len(group) + 1) for amount, group in raise_layers if group) / contested
        threshold = fair_share + (0.14 if cost else 0.08)
        if (value_equity > threshold
                and raise_ev > max(0.0, passive_ev) + 0.05 * raise_cost):
            return Action.raise_to(target)

    # Small heads-up c-bet: we made the last preflop raise and the flop is checked to us.
    if SMALL_CBET and passive.kind == "check" and len(state.board) == 3 and len(live) == 1 and live[0].status == "active":
        last_pre_raiser = None
        for event in state.history:
            if event.kind == "board":
                break
            if event.kind == "raise":
                last_pre_raiser = event.seat
        bet = state.can("raise")
        if bet and last_pre_raiser == state.seat and equity >= .5 - SMALL_CBET_MARGIN:
            size = hero.bet + max(1, int(SMALL_CBET_FRAC * state.pot))
            return Action.raise_to(int(min(bet.max_amount, max(bet.min_amount, size))))

    if passive.kind == "fold" and not state.can("fold"):
        first = state.legal_actions[0]
        return Action(first.kind, first.min_amount)
    return passive


def aggregate_orderings(hero, records):
    """Exact masses of three-player weak orders, excluding shared hidden cards.

    records[j][i] is opponent j's (score, weight) for the same deck card i.
    Sorted prefix sums integrate opponent ordering in O(deck size * log size).
    """
    ordered = sorted(records[1])
    scores = [score for score, _ in ordered]
    prefix = [0.0]
    for _, weight in ordered:
        prefix.append(prefix[-1] + weight)
    total = prefix[-1]
    below_hero = prefix[bisect_left(scores, hero)]
    through_hero = prefix[bisect_right(scores, hero)]
    equal_hero = through_hero - below_hero
    masses = {}
    for first, weight in records[0]:
        below = prefix[bisect_left(scores, first)]
        through = prefix[bisect_right(scores, first)]
        equal = through - below
        if first < hero:
            bins = (((2, 1, 0), below), ((2, 0, 0), equal),
                    ((2, 0, 1), below_hero - through),
                    ((1, 0, 1), equal_hero), ((1, 0, 2), total - through_hero))
        elif first == hero:
            bins = (((1, 1, 0), below_hero), ((0, 0, 0), equal_hero),
                    ((0, 0, 2), total - through_hero))
        else:
            bins = (((1, 2, 0), below_hero), ((0, 2, 0), equal_hero),
                    ((0, 2, 1), below - through_hero),
                    ((0, 1, 1), equal), ((0, 1, 2), total - through))
        for key, amount in bins:
            masses[key] = masses.get(key, 0.0) + weight * amount
    for (first, w0), (second, w1) in zip(*records):
        key = (int(hero > first) + (hero > second),
               int(first > hero) + (first > second),
               int(second > hero) + (second > first))
        masses[key] = masses.get(key, 0.0) - w0 * w1
    # Impossible bins can retain tiny cancellation residue; weights are >= 0.
    return {key: weight for key, weight in masses.items() if weight > 0.0}


def showdown_worlds(cards, board, opponents, discarded=(), exposed=(),
                    dead_public=(), ranges=(), exact=False):
    """Joint outcomes, retaining who wins opponent-only side pots.

    All fixed hero pairs share the same runouts and opponent hands. Evaluating
    point value after settlement, before averaging, preserves bust risk.
    """
    hole = tuple(_CARD[c] for c in cards)
    community = tuple(_CARD[c] for c in board)
    hands = ((hole[1], hole[2]), (hole[0], hole[2]), (hole[0], hole[1])) if len(hole) == 3 else (hole,)
    fixed = tuple(tuple(_CARD[c] for c in xs) for xs in exposed) if exposed else ((),) * opponents
    blocked = set(hole + community + tuple(_CARD[c] for c in tuple(discarded) + tuple(dead_public)))
    for known in fixed:
        blocked.update(known)
    deck = [card for card in _DECK if card not in blocked]
    if exact and len(hole) == 2 and len(community) == 5 and opponents == 2 and all(len(k) == 1 for k in fixed):
        # Compress the exact joint posterior into the possible weak orderings.
        # Opponent-vs-opponent order matters even when hero loses or folds.
        hero = _EVALUATE(community + hole)
        records = []
        for j, known in enumerate(fixed):
            contexts = ranges[j] if ranges else ()
            records.append(tuple((_EVALUATE(community + known + (card,)),
                                  _range_weight(known + (card,), contexts) if contexts else 1.0)
                                 for card in deck))
        masses = aggregate_orderings(hero, records)
        return tuple((weight, (scores[0],), scores[1:]) for scores, weight in masses.items())
    if exact and len(hole) == 2 and len(community) == 5 and opponents == 1 and len(fixed[0]) == 1:
        hero_score = _EVALUATE(community + hole)
        context = ranges[0] if ranges else ()
        return tuple(((_range_weight(fixed[0] + (card,), context) if context else 1.0),
                      (hero_score,), (_EVALUATE(community + fixed[0] + (card,)),))
                     for card in deck)
    seed = 2166136261
    for card in sorted(set(cards) | set(board) | set(discarded)):
        seed = ((seed ^ (_INDEX[card] + 1)) * 16777619) & 0xFFFFFFFF
    seed ^= opponents * 104729
    sample = random.Random(seed).sample
    missing = 5 - len(community)
    draws = missing + sum(2 - len(k) for k in fixed)
    result = []
    for _ in range(24 if opponents <= 3 else 16):
        picked = sample(deck, draws)
        completed = community + tuple(picked[:missing])
        scores = []
        at = missing
        weight = 1.0
        for j, known in enumerate(fixed):
            need = 2 - len(known)
            enemy = known + tuple(picked[at:at + need])
            at += need
            scores.append(_EVALUATE(completed + enemy))
            if ranges:
                weight *= _range_weight(enemy, ranges[j])
        result.append((weight, tuple(_EVALUATE(completed + hand) for hand in hands), tuple(scores)))
    return tuple(result)


def point_action_values(state, candidates, worlds=None):
    """Expected points by action and fixed pair, using the actual payout ladder.

    Opponents complete calls to the proposed street target, capped by their
    stacks; subsequent streets check down. Raises receive no assumed fold
    equity. This explicit continuation approximation is shared by all actions.
    """
    seats = sorted(state.seats, key=lambda s: s.seat)
    n = len(seats)
    if [s.seat for s in seats] != list(range(n)):
        raise ValueError("expected a seat entry for each table position")
    ledger = contributions(state)
    committed = tuple(ledger[i] for i in range(n))
    if sum(committed) != state.pot:
        raise ValueError("hand commitments do not match the public pot")
    free = tuple(s.stack for s in seats)
    starts = tuple(free[i] + committed[i] for i in range(n))
    alive = tuple(s.status != "busted" for s in seats)
    eligible = tuple(s.status in ("active", "all_in") for s in seats)
    hero = state.seat
    live = [s for s in seats if s.seat != hero and eligible[s.seat]]
    pairs = 3 if len(state.cards) == 3 else 1
    score_points = prepare_point_value(state.config.payouts, hero, starts, alive)
    if worlds is None:
        worlds = showdown_worlds(
            state.cards, state.board, len(live), tuple(state.variant.get("discarded", ())),
            tuple(tuple(s.shown_cards) for s in live),
            tuple(c for s in seats for c in s.shown_cards), opponent_ranges(state, live), exact=True)
    scenarios = []
    for action in candidates:
        contenders = list(eligible)
        additions = [0] * n
        target = action.amount if action.kind == "raise" else max(s.bet for s in seats)
        if action.kind == "fold":
            contenders[hero] = False
        elif action.kind == "call":
            additions[hero] = min(state.to_call, free[hero])
        elif action.kind == "raise":
            additions[hero] = target - seats[hero].bet
        if sum(contenders) > 1:
            for opponent in live:
                if opponent.status == "active":
                    additions[opponent.seat] = min(opponent.stack, max(0, target - opponent.bet))
        if any(add < 0 or add > free[i] for i, add in enumerate(additions)):
            raise ValueError("projected commitment exceeds available stack")
        remaining = tuple(free[i] - additions[i] for i in range(n))
        invested = tuple(committed[i] + additions[i] for i in range(n))
        base, pots = prepare_settlement(remaining, invested, tuple(contenders), state.button)
        scenarios.append((base, pots, {}))
    totals = [[0.0] * pairs for _ in candidates]
    point_cache = {}
    total_weight = 0.0
    scores = [0] * n
    for weight, hero_scores, enemy_scores in worlds:
        if len(hero_scores) != pairs or len(enemy_scores) != len(live) or weight < 0:
            raise ValueError("invalid joint showdown world")
        total_weight += weight
        for opponent, score in zip(live, enemy_scores):
            scores[opponent.seat] = score
        for pair, score in enumerate(hero_scores):
            scores[hero] = score
            for a, (base, pots, outcome_cache) in enumerate(scenarios):
                winners = []
                for _, group in pots:
                    best = max(scores[i] for i in group)
                    winners.append(tuple(i for i in group if scores[i] == best))
                signature = tuple(winners)
                value = outcome_cache.get(signature)
                if value is None:
                    terminal = list(base)
                    for (amount, _), won in zip(pots, winners):
                        share, remainder = divmod(amount, len(won))
                        for seat in won:
                            terminal[seat] += share
                        if remainder:
                            first = min(won, key=lambda seat: (seat - state.button - 1) % n)
                            terminal[first] += remainder
                    terminal = tuple(terminal)
                    value = point_cache.get(terminal)
                    if value is None:
                        value = score_points(terminal)
                        point_cache[terminal] = value
                    outcome_cache[signature] = value
                totals[a][pair] += weight * value
    if total_weight <= 0:
        raise ValueError("showdown worlds must have positive weight")
    return tuple(tuple(value / total_weight for value in values) for values in totals)


def terminal_point_call(state, proposal):
    """Protect tournament equity on a terminal, heads-up-in-hand call.

    The complete v7 policy proposes first, preserving its reshoves, c-bets,
    selections and chart folds. Only an existing CALL can be vetoed. One of
    the two contenders must be all-in after calling; folded survivors still
    count in the actual payout calculation. No blanket tiny-stack threshold.
    """
    if proposal.kind != "call" or state.phase != "betting" or not state.can("fold"):
        return proposal
    if sum(s.status != "busted" for s in state.seats) < 3:
        return proposal  # With two survivors, points are affine in chips.
    hero = next(s for s in state.seats if s.seat == state.seat)
    live = [s for s in state.seats if s.seat != state.seat and s.status in ("active", "all_in")]
    cost = min(state.to_call, hero.stack)
    if cost <= 0 or len(live) != 1 or (live[0].status != "all_in" and cost < hero.stack):
        return proposal
    fold_values, call_values = point_action_values(state, (Action.fold(), Action.call()))
    if max(call_values) + 1e-10 < max(fold_values):
        return Action.fold()
    return proposal


def decide(state: GameState) -> Action:
    return terminal_point_call(state, decide_v7(state))


class Agent(poker_agent_sdk.Agent):
    def act(self, state: GameState, memory: bytes) -> tuple[Action, bytes]:
        # The public current-hand history supplies all information this first
        # baseline uses. Ignoring memory also makes truncated/invalid bytes safe.
        return decide(state), b""
