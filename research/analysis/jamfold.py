"""Jam/fold equilibrium (chip EV) for the 3-card variant, by table size, position and stack depth.

Game per spot: everyone folds to the shover; shover chooses jam (all-in for S bb) or fold; players
behind, in order, choose call or fold; the first caller ends the action (no overcalls modeled).
Blinds 0.5/1, no ante (the competition default), all stacks equal to S. Hands are the K equity
buckets from bucket_matrix.py; E[i, j] = P(bucket i beats bucket j) heads-up at showdown.
Solved with fictitious play over bucket strategies; reports exploitability (best-response gain) so
convergence can be checked. Chip EV, not ICM: this is the pre-ICM baseline.

Simplifications to keep in mind: no overcalls/3-way all-ins; independence between callers' hands
(card removal only inside E); equal stacks; no limp/raise-fold options; flop selection modeled as
"keep best made pair" for both players.

Usage: python analysis/jamfold.py --k 40 --iters 4000
Writes data/derived/jamfold_k<K>.json and prints a summary table.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def order_for(n):
    """Preflop action order with blinds posted: (name, blind) list. Heads-up: SB(button) then BB."""
    if n == 2:
        return [("SB", 0.5), ("BB", 1.0)]
    names = {3: ["BTN"], 4: ["CO", "BTN"], 5: ["HJ", "CO", "BTN"], 6: ["LJ", "HJ", "CO", "BTN"],
             7: ["UTG+1", "LJ", "HJ", "CO", "BTN"], 8: ["UTG", "UTG+1", "LJ", "HJ", "CO", "BTN"]}[n]
    return [(x, 0.0) for x in names] + [("SB", 0.5), ("BB", 1.0)]


def solve_spot(E, w, S, b_s, behind, iters):
    """behind: list of caller blinds in action order. Returns jam probs, call probs, exploitability."""
    K = len(w)
    m = len(behind)
    dead = [1.5 - b_s - b for b in behind]
    jam = np.ones(K) * 0.5
    call = [np.ones(K) * 0.5 for _ in range(m)]
    jam_sum = np.zeros(K)
    call_sum = [np.zeros(K) for _ in range(m)]

    def shover_ev(call_strats):
        q = [float(w @ c) for c in call_strats]
        ev = np.zeros(K)
        reach = 1.0
        for i in range(m):
            pot = 2 * S + dead[i]
            ev += reach * (E * (w * call_strats[i])[None, :]).sum(1) * pot - reach * q[i] * S
            reach *= 1 - q[i]
        ev += reach * (1.5 - b_s)
        return ev  # jam EV per bucket; fold EV is -b_s

    def caller_ev(i, jam_strat):
        r = w * jam_strat
        if r.sum() <= 0:
            return np.full(K, -1e9)
        r = r / r.sum()
        pot = 2 * S + dead[i]
        return ((1 - E) * r[:, None]).sum(0) * pot - S  # call EV per bucket; fold EV is -behind[i]

    for t in range(1, iters + 1):
        avg_jam = jam_sum / max(1, t - 1) if t > 1 else jam
        avg_call = [cs / max(1, t - 1) if t > 1 else c for cs, c in zip(call_sum, call)]
        jam = (shover_ev(avg_call) > -b_s).astype(float)
        call = [(caller_ev(i, avg_jam) > -behind[i]).astype(float) for i in range(m)]
        jam_sum += jam
        for i in range(m):
            call_sum[i] += call[i]
    jam_avg = jam_sum / iters
    call_avg = [cs / iters for cs in call_sum]

    # Exploitability: each player's best-response gain vs the others' average strategies (bb/hand).
    ev_j = shover_ev(call_avg)
    cur = float(w @ (jam_avg * ev_j + (1 - jam_avg) * -b_s))
    br = float(w @ np.maximum(ev_j, -b_s))
    gains = [br - cur]
    p_jam = float(w @ jam_avg)
    q = [float(w @ c) for c in call_avg]
    reach = 1.0
    for i in range(m):
        ev_c = caller_ev(i, jam_avg)
        cur_c = float(w @ (call_avg[i] * ev_c + (1 - call_avg[i]) * -behind[i]))
        br_c = float(w @ np.maximum(ev_c, -behind[i]))
        gains.append(p_jam * reach * (br_c - cur_c))  # weighted by how often this decision happens
        reach *= 1 - q[i]
    return jam_avg, call_avg, gains


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=40)
    ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--stacks", type=float, nargs="+", default=[3, 5, 7, 10, 12, 15, 20])
    ap.add_argument("--players", type=int, nargs="+", default=[2, 3, 4, 6, 8])
    args = ap.parse_args()
    E = np.load(ROOT / f"data/derived/bucket_equity_k{args.k}.npy")
    b = pd.read_csv(ROOT / f"data/derived/buckets_k{args.k}.csv")
    w = b.groupby("bucket").combos.sum().reindex(range(args.k)).to_numpy(float)
    w = w / w.sum()

    out = []
    for n in args.players:
        order = order_for(n)
        for p, (name, b_s) in enumerate(order[:-1]):
            behind = [bl for _, bl in order[p + 1:]]
            behind_names = [nm for nm, _ in order[p + 1:]]
            for S in args.stacks:
                jam, calls, gains = solve_spot(E, w, S, b_s, behind, args.iters)
                rec = {"players": n, "pos": name, "stack_bb": S, "jam_pct": float(w @ jam),
                       "jam_by_bucket": jam.round(3).tolist(),
                       "call_pct": {nm: float(w @ c) for nm, c in zip(behind_names, calls)},
                       "call_by_bucket": {nm: c.round(3).tolist() for nm, c in zip(behind_names, calls)},
                       "exploitability_bb": [round(g, 4) for g in gains]}
                out.append(rec)
    path = ROOT / f"data/derived/jamfold_k{args.k}.json"
    path.write_text(json.dumps(out))
    print(f"wrote {path}  (k={args.k}, iters={args.iters})")
    print("\nJam % of all deals (chip EV equilibrium) | BB call % vs that jam | max exploitability bb/hand")
    for n in args.players:
        df = pd.DataFrame([r for r in out if r["players"] == n])
        tab = df.pivot(index="pos", columns="stack_bb", values="jam_pct")
        tab = tab.reindex([nm for nm, _ in order_for(n)[:-1]])
        print(f"\n{n}-handed jam%:")
        print((tab * 100).round(0).to_string())
        bb = df.assign(bbcall=df.call_pct.map(lambda d: d.get("BB", np.nan))).pivot(index="pos", columns="stack_bb", values="bbcall")
        bb = bb.reindex([nm for nm, _ in order_for(n)[:-1]])
        print(f"{n}-handed BB call% vs each position's jam:")
        print((bb * 100).round(0).to_string())
        print("max exploitability (bb/hand):", round(max(max(r["exploitability_bb"]) for r in out if r["players"] == n), 4))


if __name__ == "__main__":
    main()
