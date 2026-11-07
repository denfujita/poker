"""Replay participant hand histories into flat tables for opponent profiling.

Outputs (CSV, one directory per round) under data/derived/<tournament_id>/:
  actions.csv    one row per betting action (fold/check/call/raise) by any seat
  showdowns.csv  one row per seat that showed its retained cards at showdown
  seats.csv      one row per (table, seat): team, final points, bust hand, chips by hand milestones

Raw files are read-only inputs; nothing is imputed. Opponent hidden cards appear only when shown.

Usage: python analysis/extract.py data/raw/hands-<id>.jsonl.gz [--max-tables N]
"""

import argparse
import csv
import gzip
import json
import subprocess
from pathlib import Path

RANKS = "23456789TJQKA"


def tables(path):
    with gzip.open(path, "rt") as fh:
        header = json.loads(fh.readline())
        while True:
            public = fh.readline()
            if not public:
                return
            private = json.loads(fh.readline())
            yield header, json.loads(public), private["you"]


def replay_hand(hand, nseats):
    """Yield per-action dicts with the public state just before each betting action."""
    bb = hand["blinds"][1]
    start = hand["stacks_before"]
    total = [0] * nseats  # chips committed this hand
    street_bet = [0] * nseats
    street = 0
    folded = [False] * nseats
    exposed = [None] * nseats
    raises_this_street = 0
    board = []
    acted_preflop = [False] * nseats
    for index, e in enumerate(hand["events"]):
        k, s = e["kind"], e.get("seat")
        if k == "ante":
            total[s] += e["amount"]
        elif k == "blind":
            total[s] += e["amount"]
            street_bet[s] += e["amount"]
        elif k == "board":
            street += 1
            street_bet = [0] * nseats
            raises_this_street = 0
            board += e["cards"]
        elif k == "reveal":
            exposed[s] = e["cards"][0]
        elif k in ("fold", "check", "call", "raise"):
            pot = sum(total)
            max_bet = max(street_bet)
            to_call = max(0, max_bet - street_bet[s])
            stack_left = start[s] - total[s]
            live = [i for i in range(nseats) if not folded[i] and start[i] > 0]
            eff = max((min(stack_left, start[i] - total[i]) for i in live if i != s), default=0)
            row = {
                "event_index": index,
                "seat": s,
                "street": street,
                "action": k,
                "bb": bb,
                "pot_before": pot,
                "to_call": to_call,
                "stack_before_action_bb": stack_left / bb,
                "eff_stack_bb": eff / bb,
                "hand_start_stack_bb": start[s] / bb,
                "n_live": len(live),
                "raises_this_street": raises_this_street,
                "first_preflop_action": street == 0 and not acted_preflop[s],
                "exposed": exposed[s] or "",
                "board": "".join(board),
            }
            if k == "call":
                total[s] += e["amount"]
                street_bet[s] += e["amount"]
                row["added"] = e["amount"]
            elif k == "raise":
                added = e["amount"] - street_bet[s]
                total[s] += added
                street_bet[s] = e["amount"]
                raises_this_street += 1
                row["added"] = added
                row["raise_to"] = e["amount"]
                row["raise_to_bb"] = e["amount"] / bb
                row["size_pot_frac"] = (added - to_call) / (pot + to_call) if pot + to_call else 0.0
            else:
                row["added"] = 0
            row["all_in"] = k in ("call", "raise") and total[s] >= start[s]
            if k == "fold":
                folded[s] = True
            if street == 0:
                acted_preflop[s] = True
            yield row
    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history", type=Path)
    ap.add_argument("--max-tables", type=int, default=0)
    args = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    sha = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "no-git"

    out_dir = None
    writers = {}
    files = []
    n_tables = 0
    for header, table, own in tables(args.history):
        if out_dir is None:
            out_dir = root / "data" / "derived" / header["tournament_id"]
            out_dir.mkdir(parents=True, exist_ok=True)
            names = {e["entry_id"]: e["team_name"] for e in header["entries"]}
            (out_dir / "meta.json").write_text(json.dumps({"source": str(args.history), "code_sha": sha, "you": header["you"]}, indent=1))
        if args.max_tables and n_tables >= args.max_tables:
            break
        n_tables += 1
        seats = table["seats"]
        nseats = len(seats)
        team = [names.get(e, e) for e in seats]
        tid = f"{table['iteration']}-{table['table']}"
        bust_hand = [None] * nseats
        for hand in table["hands"]:
            hand_no = hand["hand"]
            for row in replay_hand(hand, nseats):
                s = row["seat"]
                row.update(table=tid, hand=hand_no, team=team[s], filler=table["fillers"][s], button=hand["button"],
                           pos_from_button=(s - hand["button"]) % nseats, is_me=(s == own["seat"]))
                _write(writers, files, out_dir, "actions", row)
            shown = {}
            exposed = {}
            for e in hand["events"]:
                if e["kind"] == "reveal":
                    exposed[e["seat"]] = e["cards"][0]
                elif e["kind"] == "show":
                    shown[e["seat"]] = e["cards"]
            board = [c for e in hand["events"] if e["kind"] == "board" for c in e["cards"]]
            for s, cards in shown.items():
                _write(writers, files, out_dir, "showdowns", {
                    "table": tid, "hand": hand_no, "seat": s, "team": team[s], "filler": table["fillers"][s],
                    "retained": "".join(cards), "exposed": exposed.get(s, ""), "board": "".join(board),
                    "net_chips": hand["stacks_after"][s] - hand["stacks_before"][s],
                    "start_stack_bb": hand["stacks_before"][s] / hand["blinds"][1], "is_me": s == own["seat"],
                })
            for s in range(nseats):
                if bust_hand[s] is None and hand["stacks_before"][s] > 0 and hand["stacks_after"][s] == 0:
                    bust_hand[s] = hand_no
        last = table["hands"][-1]
        for s in range(nseats):
            _write(writers, files, out_dir, "seats", {
                "table": tid, "seat": s, "team": team[s], "filler": table["fillers"][s], "is_me": s == own["seat"],
                "points": last["equity_after"][s], "bust_hand": bust_hand[s] or "", "hands_played": last["hand"],
                "payouts": "/".join(map(str, table["payouts"])),
            })
    for fh in files:
        fh.close()
    print(f"tables={n_tables} -> {out_dir}")


def _write(writers, files, out_dir, name, row):
    if name not in writers:
        fh = open(out_dir / f"{name}.csv", "w", newline="")
        files.append(fh)
        fields = list(dict.fromkeys(list(row) + _extra(name)))
        writers[name] = (csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"), set())
        writers[name][0].writeheader()
    writers[name][0].writerow(row)


def _extra(name):
    return ["added", "raise_to", "raise_to_bb", "size_pot_frac", "all_in", "table", "hand", "team", "filler",
            "button", "pos_from_button", "is_me"] if name == "actions" else []


if __name__ == "__main__":
    main()
