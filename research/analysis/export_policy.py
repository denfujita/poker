"""Export the runtime preflop policy file shipped next to agent.py.

preflop_policy.json:
  combo:  {sorted 3-card string: [pct, bucket]}  pct = combo-weighted percentile of true 3-card HU equity
          (0 = best), bucket = equity bucket 0..K-1 (0 = strongest) used by the jam/fold solver.
  jam:    {players: {position: {stack_bb: [K jam probabilities by bucket]}}}       (full solver policy)
  call:   {players: {jammer_pos: {stack_bb: {caller_pos: [K call probabilities]}}}} (full solver policy)
Source: data/derived/{buckets_k40.csv, jamfold_k40.json} (see jamfold.py for the model and its limits).

Usage: python analysis/export_policy.py --k 40 --out <bot_dir>/preflop_policy.json
"""

import argparse
import itertools
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preflop_equity import DECK, canonical, label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=40)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    b = pd.read_csv(ROOT / f"data/derived/buckets_k{args.k}.csv")
    cls = {c: (round(float(p), 4), int(k)) for c, p, k in zip(b["class"], b.pct_mid, b.bucket)}
    combo = {"".join(sorted(c)): list(cls[label(canonical(c))]) for c in itertools.combinations(DECK, 3)}
    jf = json.loads((ROOT / f"data/derived/jamfold_k{args.k}.json").read_text())
    jam, call = {}, {}
    for r in jf:
        n, pos, s = str(r["players"]), r["pos"], str(int(r["stack_bb"]))
        jam.setdefault(n, {}).setdefault(pos, {})[s] = r["jam_by_bucket"]
        call.setdefault(n, {}).setdefault(pos, {})[s] = r["call_by_bucket"]
    out = {"k": args.k, "combo": combo, "jam": jam, "call": call}
    args.out.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {args.out} ({args.out.stat().st_size} bytes, {len(combo)} combos)")


if __name__ == "__main__":
    main()
