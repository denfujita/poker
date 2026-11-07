"""Synthetic SDK regressions; no tournament histories or account information.

Run with the starter kit virtualenv: python tools/check_side_pots.py agent.py.
Pass --baseline OLD_AGENT to demonstrate the former profitable-call fold.
"""
import argparse
import importlib.util
from dataclasses import replace
from pathlib import Path

from poker_agent_protocol.game import (
    BlindLevel, Event, GameState, LegalAction, Seat, TableConfig, is_legal,
)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(board=("As", "Ah", "Ac", "7d", "2h"), cards=("Kh", "Kd"),
            shown=("Kd", "Ad", "3c"), committed=(100, 100, 1000),
            stacks=(900, 0, 0), bets=(0, 0, 900), statuses=("active", "all_in", "all_in"),
            cost=900, legal=None):
    # Earlier commitments were matched; the deep player makes the river bet.
    history = [Event("blind", 0, 50), Event("blind", 1, 100),
               Event("call", 2, 100), Event("call", 0, 50),
               Event("board", cards=board[:3])]
    history += [Event("reveal", i, cards=(card,)) for i, card in enumerate(shown)]
    history += [Event("check", 0), Event("check", 2), Event("board", cards=board[3:4]),
                Event("check", 0), Event("check", 2), Event("board", cards=board[4:]),
                Event("check", 0), Event("raise", 2, bets[2])]
    seats = tuple(Seat(i, stacks[i], bets[i], statuses[i], (shown[i],)) for i in range(3))
    blinds = BlindLevel(50, 100)
    config = TableConfig("synthetic-side-pots", 0, 3, "bay_area", 1000,
                         (blinds,), 20, 250, (50, 30, 20), 1, 65536, 100)
    history = tuple(history)
    return GameState(history, 1, 0, cards, board, sum(committed), cost,
                     legal or (LegalAction("fold"), LegalAction("call")), history,
                     seats, 2, 0, blinds, 20, 3, (), config,
                     {"discarded": ("Qs",)}, "betting", 100)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    bot = load(args.candidate, "side_pot_candidate")
    checks = 0

    def check(condition, description):
        nonlocal checks
        assert condition, description
        checks += 1

    state = fixture()
    if args.baseline:
        old = load(args.baseline, "side_pot_baseline")
        check(old.Agent().act(state, b"")[0].kind == "fold", "baseline reproduces bad fold")
    action, _ = bot.Agent().act(state, b"")
    check(action.kind == "call", "call guaranteed profitable side pot")
    check(is_legal(action, state.legal_actions), "side-pot action is legal")
    committed = bot.contributions(state)
    live = list(state.seats[1:])
    layers = bot.pot_layers(state, committed, 900, live)
    check(layers == ((300, (0, 1)), (1800, (1,))), "separate main and side contenders")
    groups = ((0, 1), (1,))
    shares = dict(zip(groups, bot.equities(
        state.cards, state.board, 2, ("Qs",), (("Ad",), ("3c",)),
        ("Ad", "3c", "Kd"), contender_groups=groups)))
    check(shares == {(0, 1): (0.0,), (1,): (1.0,)}, "main lost but side always won")
    check(bot.layer_payout(layers, shares) - 900 == 900, "positive 900-chip call EV")

    # The board plays: ties split only among eligible players in each pot.
    tie_board = ("As", "Ks", "Qs", "Js", "Ts")
    tied = dict(zip(groups, bot.equities(("2c", "2d"), tie_board, 2,
                                       exposed=(("3c",), ("4c",)), contender_groups=groups)))
    check(abs(tied[(0, 1)][0] - 1 / 3) < 1e-12 and tied[(1,)][0] == .5,
          "three-way main tie and heads-up side tie")
    check(abs(bot.layer_payout(layers, tied) - 1000) < 1e-9, "tie payout totals correctly")

    # A folded player's chips remain; its exposed card is still a blocker.
    folded = replace(state, pot=1300, seats=state.seats + (Seat(3, 0, 0, "folded", ("Jc",)),))
    folded_layers = bot.pot_layers(folded, {0: 100, 1: 100, 2: 1000, 3: 100}, 900, live)
    check(folded_layers == ((400, (0, 1)), (1800, (1,))), "folded chips contribute, folded hand cannot win")

    # A short hero cannot win the side pot above its contribution cap.
    short = replace(state, pot=1150, to_call=950,
                    seats=(Seat(0, 50, 0, "active", ("Kd",)),
                           Seat(1, 0, 50, "all_in", ("Ad",)),
                           Seat(2, 0, 950, "all_in", ("3c",))))
    check(bot.pot_layers(short, {0: 50, 1: 100, 2: 1000}, 50, list(short.seats[1:])) ==
          ((300, (0, 1)),), "no hero eligibility above cap")
    short_history = (Event("blind", 0, 25), Event("blind", 1, 50),
                     Event("call", 2, 50), Event("call", 0, 25), Event("check", 1),
                     Event("board", cards=state.board[:3]),
                     Event("reveal", 0, cards=("Kd",)), Event("reveal", 1, cards=("Ad",)),
                     Event("reveal", 2, cards=("3c",)),
                     Event("check", 0), Event("check", 1), Event("check", 2),
                     Event("board", cards=state.board[3:4]),
                     Event("check", 0), Event("check", 1), Event("check", 2),
                     Event("board", cards=state.board[4:]),
                     Event("check", 0), Event("raise", 1, 50), Event("raise", 2, 950))
    short = replace(short, history=short_history, events=short_history, blinds=BlindLevel(25, 50))
    check(bot.Agent().act(short, b"")[0].kind == "fold", "fold when side pot lies above hero's cap")

    # Unmatched hero excess is returned without a risk discount.
    excess = replace(state, pot=200)
    excess_layers = bot.pot_layers(excess, {0: 50, 1: 50, 2: 100}, 150, live)
    check(excess_layers == ((150, (0, 1)), (100, (1,)), (100, ())), "unmatched excess separated")
    certain = {(0, 1): (0.0,), (1,): (0.0,), (): (1.0,)}
    check(bot.layer_payout(excess_layers, certain, margin=.25) == 100,
          "uncalled return is not discounted")

    # The engine silently returns unmatched bets at completed street boundaries.
    refund = replace(state, history=(Event("blind", 0, 50), Event("blind", 1, 100),
                     Event("raise", 2, 1000), Event("call", 0, 50),
                     Event("board", cards=("As", "Ah", "Ac"))))
    check(bot.contributions(refund) == {0: 100, 1: 100, 2: 100}, "prior uncalled raise refunded")
    ante_refund = replace(state, history=(Event("ante", 0, 100), Event("ante", 1, 50),
                          Event("ante", 2, 50), Event("blind", 0, 50), Event("blind", 2, 100)))
    check(bot.contributions(ante_refund) == {0: 100, 1: 50, 2: 150}, "ante trimming separate from blinds")

    # Pending active opponents still contest layers they can afford. No future
    # call chips are added to the passive pot merely to justify a call.
    pending = replace(state, pot=120, seats=(Seat(0, 900, 0, "active"),
                      Seat(1, 900, 10, "active"), Seat(2, 900, 100, "active")))
    pending_layers = bot.pot_layers(pending, {0: 10, 1: 10, 2: 100}, 90, list(pending.seats[1:]))
    check(pending_layers == ((210, (0, 1)),), "pending active response preserves single-pot model")

    # Default callers retain the old return shape and exactly the same values.
    normal_args = (("Kh", "Kd"), ("2c", "7s", "9d"), 2)
    original = bot.equities(*normal_args)
    grouped = bot.equities(*normal_args, contender_groups=((0, 1),))
    check(grouped == (original,), "single-pot sampling unchanged")

    # All layers must use ONE retained pair, never the best pair per pot.
    discard_shares = {(0, 1): (.9, .1, .4), (1,): (.1, .9, .6)}
    payouts = tuple(bot.layer_payout(((100, (0, 1)), (200, (1,))), discard_shares, i) for i in range(3))
    check(payouts == (110.0, 190.0, 160.0), "pair values sum across pots before choice")
    check(max(payouts) < 100 * .9 + 200 * .9, "no incompatible pairs across pots")

    # A projected raise changes both pot amounts and eligibility; it cannot use
    # a single equity normalized for the call pot as if the pots were identical.
    raising = replace(state, pot=1200, seats=(replace(state.seats[0], stack=1800), state.seats[1],
                      Seat(2, 900, 900, "active", ("3c",))),
                      legal_actions=(LegalAction("fold"), LegalAction("call"), LegalAction("raise", 1800, 1800)))
    raise_layers = bot.pot_layers(raising, committed, 1800, list(raising.seats[1:]), {2: 900})
    check(raise_layers == ((300, (0, 1)), (3600, (1,))), "projected raise layers recomputed")
    check(bot.layer_payout(raise_layers, shares) - 1800 == 1800, "raise payout uses its own layers")

    print({"passed": checks, "failed": 0})


if __name__ == "__main__":
    main()
