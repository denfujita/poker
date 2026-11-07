"""Where does OUR bot lose chips? Streams a raw hand history and follows only our seat.

Per hand: net chips (in starting stacks: 1.0 = 100 bb at 20 bb... no, = the 2000-chip starting stack),
classified by how the hand ended for us and the biggest decision we made. Also classifies the hand we busted on.

Usage: python analysis/diagnose_me.py data/raw/hands-<id>.jsonl.gz [--out results/diagnose/<id>.json]
"""

import argparse
import collections
import gzip
import json
from pathlib import Path

START = 2000


def scan(path):
    agg = collections.defaultdict(lambda: [0, 0.0, 0])  # category -> [hands, net_chips, wins]
    bust = collections.Counter()
    bust_hand_no = []
    tables = 0
    with gzip.open(path, "rt") as fh:
        fh.readline()
        while True:
            pub = fh.readline()
            if not pub:
                break
            table = json.loads(pub)
            me = json.loads(fh.readline())["you"]["seat"]
            tables += 1
            n = len(table["seats"])
            for hand in table["hands"]:
                start = hand["stacks_before"][me]
                if start <= 0:
                    continue
                net = hand["stacks_after"][me] - start
                committed = 0
                street_bet = [0] * n
                street = 0
                folded = showed = False
                big = None  # biggest single decision: (cost_share_of_stack, kind, street, all_in)
                for e in hand["events"]:
                    k, s = e["kind"], e.get("seat")
                    if k == "board":
                        street += 1
                        street_bet = [0] * n
                    elif k == "blind":
                        street_bet[s] += e["amount"]
                        if s == me:
                            committed += e["amount"]
                    elif k == "ante" and s == me:
                        committed += e["amount"]
                    elif k == "show" and s == me:
                        showed = True
                    elif k in ("call", "raise", "fold", "check"):
                        to_call = max(street_bet) - street_bet[s]
                        add = e["amount"] if k == "call" else (e["amount"] - street_bet[s] if k == "raise" else 0)
                        if k in ("call", "raise"):
                            street_bet[s] += add
                        if s != me:
                            continue
                        if k == "fold":
                            folded = True
                        if k in ("call", "raise"):
                            left = start - committed
                            share = add / left if left else 0
                            all_in = add >= left
                            committed += add
                            label = "call" if k == "call" else ("bet" if to_call == 0 else "raise")
                            if big is None or share > big[0]:
                                big = (share, label, street, all_in)
                st = lambda x: "pre" if x == 0 else "post"
                if folded:
                    cat = f"we folded {st(street)}"
                elif not showed:
                    cat = "won without showdown" if net > 0 else "lost without showdown (?)"
                else:
                    if big and big[0] >= 0.5:
                        cat = f"showdown after our {'all-in ' if big[3] else ''}{big[1]} >=50% stack ({st(big[2])})"
                    elif big and big[0] >= 0.15:
                        cat = f"showdown after our {big[1]} 15-50% stack ({st(big[2])})"
                    else:
                        cat = "showdown, small commitments"
                a = agg[cat]
                a[0] += 1
                a[1] += net
                a[2] += net > 0
                if hand["stacks_after"][me] == 0:
                    bust[cat] += 1
                    bust_hand_no.append(hand["hand"])
    return tables, agg, bust, bust_hand_no


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("history", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    tables, agg, bust, bh = scan(args.history)
    rows = sorted(agg.items(), key=lambda kv: kv[1][1])
    print(f"{args.history.name}: {tables} tables. Net in starting stacks (2000 chips) per table.")
    print(f"{'how the hand ended for us':58s} {'hands/tbl':>9s} {'net/tbl':>8s} {'win%':>6s} {'busts':>6s}")
    for cat, (h, net, w) in rows:
        print(f"{cat:58s} {h / tables:9.2f} {net / START / tables:+8.3f} {100 * w / h:6.1f} {bust[cat]:6d}")
    bh.sort()
    if bh:
        print(f"busts: {len(bh)} of {tables} tables; median bust hand {bh[len(bh) // 2]}; "
              f"by hand 30: {sum(x <= 30 for x in bh) / tables:.2f}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"tables": tables, "agg": agg, "bust": bust, "bust_hands": bh}, indent=1))


if __name__ == "__main__":
    main()
