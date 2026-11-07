"""Per-team behavioral profile from extracted hand histories (see extract.py).

All stats are observed frequencies from tables our bot sat at, fillers excluded.
Counts (n) are printed so small samples are visible; CIs: Wilson 95% for key rates.

Usage: python analysis/profile.py data/derived/<tournament_id> [--teams "A,B,..."]
"""

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

RANKS = "23456789TJQKA"
DEFAULT_TEAMS = ["TeamBallHog", "AZ", "pocket rockets", "Always Folds", "2 Curry", "Team 72",
                 "sandylikesfrogs", "Spartan Mathematics", "3betblind"]


def wilson(k, n):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def rate(mask_num, mask_den):
    n = int(mask_den.sum())
    k = int((mask_num & mask_den).sum())
    return k / n if n else float("nan"), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("derived", type=Path)
    ap.add_argument("--teams", default=",".join(DEFAULT_TEAMS))
    args = ap.parse_args()
    teams = [t for t in args.teams.split(",") if t]

    a = pd.read_csv(args.derived / "actions.csv", low_memory=False)
    s = pd.read_csv(args.derived / "showdowns.csv")
    seats = pd.read_csv(args.derived / "seats.csv")
    a = a[~a.filler]
    s = s[~s.filler]
    seats = seats[~seats.filler]
    for col in ("all_in", "first_preflop_action"):
        a[col] = a[col].astype(str) == "True"

    pre = a[a.street == 0]
    first = pre[pre.first_preflop_action]
    hands = first.groupby("team").size()
    vpip_hands = pre[pre.action.isin(["call", "raise"])].drop_duplicates(["table", "hand", "seat"]).groupby("team").size()
    pfr_hands = pre[pre.action == "raise"].drop_duplicates(["table", "hand", "seat"]).groupby("team").size()

    unopened = first[first.raises_this_street == 0]
    facing_raise = first[first.raises_this_street >= 1]
    big = a[(a.to_call > 0) & (a.to_call >= 0.5 * a.stack_before_action_bb * a.bb) & a.action.isin(["call", "fold"])]
    post = a[a.street >= 1]
    post_unbet = post[post.to_call == 0]
    post_facing = post[post.to_call > 0]

    rows = []
    all_teams = sorted(seats.team.unique())
    for t in all_teams:
        u = unopened[unopened.team == t]
        fr = facing_raise[facing_raise.team == t]
        bg = big[big.team == t]
        pu = post_unbet[post_unbet.team == t]
        pf = post_facing[post_facing.team == t]
        st = seats[seats.team == t]
        n_hands = int(hands.get(t, 0))
        open_raises = u[u.action == "raise"]
        bets = pu[pu.action == "raise"]
        rows.append({
            "team": t,
            "tables": len(st),
            "pts": st.points.mean(),
            "bust<=30h": (pd.to_numeric(st.bust_hand, errors="coerce") <= 30).mean(),
            "hands": n_hands,
            "VPIP": vpip_hands.get(t, 0) / n_hands if n_hands else np.nan,
            "PFR": pfr_hands.get(t, 0) / n_hands if n_hands else np.nan,
            "unopened_n": len(u),
            "open_fold": (u.action == "fold").mean(),
            "open_limp": (u.action == "call").mean(),
            "open_raise": ((u.action == "raise") & ~u.all_in).mean(),
            "open_shove": ((u.action == "raise") & u.all_in).mean(),
            "open_size_bb_med": open_raises[~open_raises.all_in].raise_to_bb.median(),
            "vsRaise_n": len(fr),
            "vsRaise_fold": (fr.action == "fold").mean(),
            "vsRaise_call": (fr.action == "call").mean(),
            "vsRaise_3bet": (fr.action == "raise").mean(),
            "bigCall_n": len(bg),
            "bigCall_rate": (bg.action == "call").mean(),
            "post_unbet_n": len(pu),
            "post_bet": (pu.action == "raise").mean(),
            "post_bet_size_med": bets.size_pot_frac.median(),
            "post_bet_allin": bets.all_in.mean() if len(bets) else np.nan,
            "post_facing_n": len(pf),
            "post_fold": (pf.action == "fold").mean(),
            "post_call": (pf.action == "call").mean(),
            "post_raise": (pf.action == "raise").mean(),
        })
    prof = pd.DataFrame(rows).set_index("team")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.float_format", lambda x: f"{x:.3f}")
    field = prof[prof.hands >= 300]
    print(f"teams={len(prof)} (with >=300 preflop decisions: {len(field)})")
    print("\n## Field quantiles (teams with >=300 hands)")
    print(field.drop(columns=["tables", "hands"]).quantile([0.1, 0.5, 0.9]).T.to_string())

    cols1 = ["tables", "pts", "bust<=30h", "hands", "VPIP", "PFR", "open_fold", "open_limp", "open_raise", "open_shove", "open_size_bb_med"]
    cols2 = ["vsRaise_n", "vsRaise_fold", "vsRaise_call", "vsRaise_3bet", "bigCall_n", "bigCall_rate"]
    cols3 = ["post_unbet_n", "post_bet", "post_bet_size_med", "post_bet_allin", "post_facing_n", "post_fold", "post_call", "post_raise"]
    sel = prof.loc[[t for t in teams if t in prof.index]]
    for title, cols in (("Preflop", cols1), ("Facing raises / big all-in decisions", cols2), ("Postflop", cols3)):
        print(f"\n## {title}: selected teams")
        print(sel[cols].to_string())

    # Correlation of style with points across the field.
    print("\n## Spearman correlation of each stat with points per table (teams with >=300 hands)")
    corr = field.drop(columns=["tables", "hands"]).corr(method="spearman")["pts"].drop("pts").sort_values()
    print(corr.to_string())

    # Preflop by stack depth for selected teams.
    first = first.assign(depth=pd.cut(first.stack_before_action_bb, [0, 10, 20, 40, 1e9], labels=["<10", "10-20", "20-40", "40+"]))
    u = first[first.raises_this_street == 0]
    print("\n## Unopened pots by stack depth (bb): share folding / shoving / raising (n)")
    for t in [t for t in teams if t in prof.index]:
        g = u[u.team == t].groupby("depth", observed=False)
        parts = []
        for d, x in g:
            if len(x):
                parts.append(f"{d}: fold {np.mean(x.action == 'fold'):.2f} shove {np.mean((x.action == 'raise') & x.all_in):.2f} "
                             f"raise {np.mean((x.action == 'raise') & ~x.all_in):.2f} (n={len(x)})")
        print(f"{t:22s} | " + " | ".join(parts))

    # Showdowns: what did they show, and how did they choose what to expose?
    print("\n## Showdown hands and exposure choice (from shown retained cards)")
    for t in [t for t in teams if t in prof.index]:
        x = s[s.team == t]
        if not len(x):
            continue
        exp_hi, pair, exp_pairs_flop, hid_pairs_flop, n = 0, 0, 0, 0, 0
        for _, r in x.iterrows():
            if not isinstance(r.exposed, str) or len(r.retained) != 4:
                continue
            c1, c2 = r.retained[:2], r.retained[2:]
            hidden = c2 if r.exposed == c1 else c1
            flop = [r.board[i:i + 2] for i in range(0, min(6, len(r.board)), 2)]
            n += 1
            exp_hi += RANKS.index(r.exposed[0]) > RANKS.index(hidden[0])
            pair += c1[0] == c2[0]
            exp_pairs_flop += any(r.exposed[0] == f[0] for f in flop)
            hid_pairs_flop += any(hidden[0] == f[0] for f in flop)
        if n:
            print(f"{t:22s} n={n:4d}  exposes higher card {exp_hi / n:.2f}  pocket pair kept {pair / n:.2f}  "
                  f"exposed pairs flop {exp_pairs_flop / n:.2f}  hidden pairs flop {hid_pairs_flop / n:.2f}")


if __name__ == "__main__":
    main()
