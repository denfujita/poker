"""Empirical likelihood of postflop actions given hand-strength percentile, from showdown hands.

For every postflop action by a non-filler opponent whose retained cards were later shown, compute q =
mid-rank percentile of their hidden card among all candidate hidden cards (unseen from a public view:
not on the board so far, not their exposed card), ranked by eval7.evaluate([exposed, h] + board_so_far).
q = 1 strongest. Then histogram q per context (street x facing-bet x action x size bin).

Because q is a percentile over candidates, its prior is ~uniform, so the q-density given an action is
proportional to the likelihood L(action | q) used to reweight candidates. CAVEAT: only showdown hands are
seen, which over-weights hands strong enough to reach showdown (bluffs that won uncontested are missing).

Usage: python analysis/action_likelihood.py data/derived/<round_id> --bins 5 --max-rows 60000
Writes bots/preflop_tables/postflop_likelihood.json and prints the table.
"""

import argparse
import json
from pathlib import Path

import eval7
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RANKS = "23456789TJQKA"
DECK = [r + s for r in RANKS for s in "shdc"]
C = {c: eval7.Card(c) for c in DECK}


def size_bin(row):
    if row.action != "raise":
        return row.action  # check / call
    if row.all_in:
        return "bet_allin"
    f = row.size_pot_frac
    return "bet_small" if f < 0.4 else "bet_med" if f < 0.8 else "bet_big"


def q_of(exposed, hidden, board):
    b = [board[i:i + 2] for i in range(0, len(board), 2)]
    seen = set(b) | {exposed}
    cand = [c for c in DECK if c not in seen]
    bc = [C[x] for x in b]
    e = C[exposed]
    vals = np.array([eval7.evaluate([e, C[h]] + bc) for h in cand])
    v = eval7.evaluate([e, C[hidden]] + bc)
    below = (vals < v).sum()
    equal = (vals == v).sum()
    return (below + equal / 2) / len(cand)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("derived", type=Path)
    ap.add_argument("--bins", type=int, default=5)
    ap.add_argument("--max-rows", type=int, default=60000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    a = pd.read_csv(args.derived / "actions.csv", low_memory=False)
    s = pd.read_csv(args.derived / "showdowns.csv")
    a = a[(a.street >= 1) & (a.filler.astype(str) != "True") & (a.is_me.astype(str) != "True")]
    a = a[a.action.isin(["check", "call", "raise"])]
    a["all_in"] = a.all_in.astype(str) == "True"
    m = a.merge(s[["table", "hand", "seat", "retained", "exposed"]], on=["table", "hand", "seat"], suffixes=("", "_sd"))
    m = m[m.exposed_sd.notna() & (m.retained.str.len() == 4)]
    if len(m) > args.max_rows:
        m = m.sample(args.max_rows, random_state=args.seed)
    m["hidden"] = [r[2:] if r[:2] == e else r[:2] for r, e in zip(m.retained, m.exposed_sd)]
    m["q"] = [q_of(e, h, b) for e, h, b in zip(m.exposed_sd, m.hidden, m.board)]
    m["facing"] = np.where(m.to_call > 0, "facing", "unbet")
    m["act"] = m.apply(size_bin, axis=1)
    m["street_name"] = m.street.map({1: "flop", 2: "turn", 3: "river"})
    edges = np.linspace(0, 1, args.bins + 1)
    m["qbin"] = np.clip(np.digitize(m.q, edges[1:-1]), 0, args.bins - 1)

    table = {}
    print(f"rows={len(m)} (showdown-only actions), bins={args.bins}; density per q-bin, weakest -> strongest; 1.0 = uniform")
    for (st, fc, act), g in m.groupby(["street_name", "facing", "act"]):
        if len(g) < 80:
            continue
        counts = np.bincount(g.qbin, minlength=args.bins) + 1.0  # +1 smoothing
        dens = counts / counts.sum() * args.bins
        table.setdefault(st, {}).setdefault(fc, {})[act] = {"n": int(len(g)), "density": [round(x, 3) for x in dens]}
        print(f"{st:5s} {fc:6s} {act:10s} n={len(g):5d} mean q {g.q.mean():.2f}  density {np.round(dens, 2)}")
    out = ROOT / "bots/preflop_tables/postflop_likelihood.json"
    out.write_text(json.dumps({"bins": args.bins, "source": str(args.derived), "note": "q-density | action from showdown hands; use as likelihood multiplier; floor it (e.g. >= 0.15) before use", "table": table}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
