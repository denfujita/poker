"""Pure chip settlement and expected tournament-point values.

All seat-indexed arguments are dense sequences, including seats already out of
the tournament. Eligibility and hand-start participation are boolean masks.
No private information or state is retained between calls.
"""

from math import isfinite

# Only immutable combinatorial topology is shared between decisions.
# NumPy's elementwise operations and bincount do not launch a BLAS pool.
import numpy as np


def _icm_topology(other_players):
    size = 1 << other_players
    members = np.array([[bool(mask & (1 << j)) for j in range(other_players)]
                        for mask in range(size)], dtype=np.float64)
    layers = []
    for depth in range(other_players + 1):
        masks = [mask for mask in range(size) if mask.bit_count() == depth]
        source, target, player = [], [], []
        for position, mask in enumerate(masks):
            for j in range(other_players):
                if not mask & (1 << j):
                    source.append(position)
                    target.append(mask | (1 << j))
                    player.append(j)
        arrays = tuple(np.array(xs, dtype=np.intp) for xs in (masks, source, target, player))
        for array in arrays:
            array.setflags(write=False)
        layers.append(arrays)
    members.setflags(write=False)
    return members, tuple(layers)


_ICM_TOPOLOGY = tuple(_icm_topology(n) for n in range(10))


def _hero_icm(stacks, payouts, hero):
    """Exact arbitrary-payout ICM, integrating only orders before hero places."""
    others = np.array([s for i, s in enumerate(stacks) if i != hero and s > 0], dtype=np.float64)
    members, layers = _ICM_TOPOLOGY[len(others)]
    removed = (members * others).sum(axis=1)
    total = float(sum(stacks))
    chance = np.zeros(len(members), dtype=np.float64)
    chance[0] = 1.0
    value = 0.0
    for depth, (masks, source, target, player) in enumerate(layers):
        if depth >= len(payouts):
            break
        scaled = chance[masks] / (total - removed[masks])
        value += float(scaled.sum()) * stacks[hero] * payouts[depth]
        if len(source):
            chance = np.bincount(target, weights=scaled[source] * others[player], minlength=len(members))
    return value


# Warm immutable-topology/NumPy dispatch during import, outside decision time.
_hero_icm((100,) * 10, tuple(range(10, 0, -1)), 0)


def _chips(values, name, size=None):
    if size is not None and len(values) != size:
        raise ValueError(f"{name} must contain one value per seat")
    if not values or any(type(value) is not int or value < 0 for value in values):
        raise ValueError(f"{name} must contain nonnegative integer chips")


def _mask(values, name, size):
    if len(values) != size or any(type(value) is not bool for value in values):
        raise ValueError(f"{name} must be a boolean mask with one value per seat")


def point_value(stacks, payouts, hero, hand_start_stacks, alive_at_hand_start):
    """Return hero's expected final points after a fully settled hand.

    Positive-stack seats receive ICM equity under the actual payout vector.
    Newly eliminated seats receive their earned finishing-place points; players
    eliminated together tie only when their hand-start stacks were equal.
    ``hero`` must have been alive at this hand's start. Previously eliminated
    players' exact finishing places cannot be recovered from these arguments.

    The common top-three payout case computes only hero's exact equity. Longer
    payout vectors use the official SDK. Heads-up values are affine in chips.
    This is a tournament-continuation model, not a future-play solver.
    """
    _chips(stacks, "stacks")
    if len(hand_start_stacks) != len(stacks):
        raise ValueError("hand_start_stacks must contain one value per seat")
    score = prepare_point_value(payouts, hero, hand_start_stacks, alive_at_hand_start)
    if any(stack and not alive for stack, alive in zip(stacks, alive_at_hand_start)):
        raise ValueError("a previously eliminated seat cannot regain chips")
    if not sum(stacks):
        raise ValueError("a settled tournament must have at least one survivor")
    return score(stacks)


def prepare_point_value(payouts, hero, hand_start_stacks, alive_at_hand_start):
    """Validate fixed hand inputs once and return a decision-local scorer.

    ``score(terminal_stacks)`` trusts terminal stacks produced by settlement:
    the same seat count, nonnegative integer chips, at least one survivor, and
    no chips at previously eliminated seats. Use ``point_value`` for untrusted
    terminal inputs. Fixed arguments are copied; no cache or state is global.
    """
    _chips(hand_start_stacks, "hand_start_stacks")
    size = len(hand_start_stacks)
    _mask(alive_at_hand_start, "alive_at_hand_start", size)
    if type(hero) is not int or not 0 <= hero < size or not alive_at_hand_start[hero]:
        raise ValueError("hero must be a seat alive at the start of this hand")
    if any(alive != (start > 0) for alive, start in zip(alive_at_hand_start, hand_start_stacks)):
        raise ValueError("hand-start stacks must match the hand-start alive mask")
    if any(not isinstance(value, (int, float)) or not isfinite(value) or value < 0
           for value in payouts):
        raise ValueError("payouts must contain finite nonnegative points")
    payouts = tuple(payouts)
    alive_count = sum(alive_at_hand_start)
    start = hand_start_stacks[hero]
    lower_starts = tuple(i for i in range(size)
                         if alive_at_hand_start[i] and hand_start_stacks[i] < start)
    equal_starts = tuple(i for i in range(size)
                         if alive_at_hand_start[i] and hand_start_stacks[i] == start)

    def score(stacks):
        total = sum(stacks)
        if stacks[hero] == 0:
            lower = sum(not stacks[i] for i in lower_starts)
            tied = sum(not stacks[i] for i in equal_starts)
            last_place = alive_count - 1 - lower
            return sum(payouts[place] if place < len(payouts) else 0.0
                       for place in range(last_place - tied + 1, last_place + 1)) / tied

        active = sum(stack > 0 for stack in stacks)
        prizes = payouts[:active]
        if not prizes:
            return 0.0
        first = stacks[hero] / total
        if active == 1:
            return float(prizes[0])
        if active == 2:
            second_prize = prizes[1] if len(prizes) > 1 else 0.0
            return second_prize + (prizes[0] - second_prize) * first
        if any(prizes[3:]):
            return _hero_icm(stacks, prizes, hero)

        value = prizes[0] * first
        others = [stack for i, stack in enumerate(stacks) if i != hero and stack > 0]
        if len(prizes) > 1 and prizes[1]:
            value += prizes[1] * first * sum(stack / (total - stack) for stack in others)
        if len(prizes) > 2 and prizes[2]:
            third = 0.0
            for i, a in enumerate(others):
                for b in others[i + 1:]:
                    third += a * b / (total - a - b) * (1 / (total - a) + 1 / (total - b))
            value += prizes[2] * first * third
        return value

    return score


def settle_pots(stacks, committed, eligible, scores, button):
    """Return every seat's integer stack after settling one sampled outcome.

    ``stacks`` are uncommitted chips; ``committed`` includes all chips already
    in the pot, after earlier street refunds. ``eligible`` is a boolean mask:
    folded and previously busted players cannot win. Larger ``scores`` win;
    ineligible scores are ignored. Eligibility is capped by each contribution.

    A unique unmatched contribution is returned to its owner. Adjacent layers
    with identical eligibility are merged, matching PokerKit. Ties split each
    pot evenly; the entire integer remainder goes to its first winner clockwise
    left of the button. An impossible contested pot without an eligible winner
    raises instead of dropping chips or awarding a short stack an unrelated pot.
    """
    base, pots = prepare_settlement(stacks, committed, eligible, button)
    size = len(stacks)
    if len(scores) != size:
        raise ValueError("scores must contain one value per seat")
    if any(allowed and (not isinstance(score, (int, float)) or not isfinite(score))
           for allowed, score in zip(eligible, scores)):
        raise ValueError("eligible players require finite numeric hand scores")

    result = list(base)
    for amount, contenders in pots:
        best = max(scores[i] for i in contenders)
        winners = [i for i in contenders if scores[i] == best]
        share, remainder = divmod(amount, len(winners))
        for seat in winners:
            result[seat] += share
        first = min(winners, key=lambda seat: (seat - button - 1) % size)
        result[first] += remainder
    return tuple(result)


def prepare_settlement(stacks, committed, eligible, button):
    """Validate one action's fixed pot inputs and compile its settlement layout.

    Returns ``(refunded_base_stacks, pots)`` as immutable tuples; each pot is
    ``(amount, eligible_seats)``. Equal eligibility layers are already merged.
    A caller can reuse this layout and its computed winner groups across all
    sampled hands. Split each pot among its tied winners, giving the entire
    remainder to the first winner clockwise left of ``button``.
    """
    _chips(stacks, "stacks")
    size = len(stacks)
    _chips(committed, "committed", size)
    _mask(eligible, "eligible", size)
    if type(button) is not int or not 0 <= button < size:
        raise ValueError("button must be a valid seat")

    result = list(stacks)
    pots = []
    previous = 0
    for level in sorted(set(committed) - {0}):
        contributors = tuple(i for i, chips in enumerate(committed) if chips >= level)
        amount = (level - previous) * len(contributors)
        previous = level
        if len(contributors) == 1:
            result[contributors[0]] += amount
            continue
        contenders = tuple(i for i in contributors if eligible[i])
        if not contenders:
            raise ValueError("contested side pot has no eligible player")
        if pots and pots[-1][1] == contenders:
            amount += pots.pop()[0]
        pots.append((amount, contenders))

    return tuple(result), tuple(pots)
