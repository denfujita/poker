"""Field-wide strategy distribution and trends across rounds, from the tracking store (see track.py).

Outputs (results/evolution/):
  teams_wide.csv       one row per (round, team): official points + key stat rates (+ n for each)
  field_quantiles.csv  per (round, stat): across-team p10/p25/p50/p75/p90, and the median of that round's top 10
  styles.csv           per (round, team): heuristic style label
Prints the same tables plus style counts per round and round-to-round style transitions.

Style labels are hand-set threshold rules for readability, not clusters fitted to data; thresholds are below.
Only tables our bot sat at are observed. A stat needs n >= MIN_N opportunities to count for a team-round.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "data/derived/tracking"
OUT = ROOT / "results/evolution"
MIN_N = 40
KEY = ["vpip", "pfr", "open_limp", "open_shove@<10", "open_shove@10-20", "open_shove@40+", "vsraise_fold",
       "vsraise_3bet", "bigcall", "bet_when_checked_flop", "bet_when_checked_river", "post_vsbet_fold",
       "post_vsbet_raise", "betsize_allin", "sd_exposes_higher", "sd_hidden_pairs_flop"]


def style(r):
    g = lambda k: r.get(k, np.nan)
    agg = g("pfr") / g("vpip") if g("vpip") else np.nan
    if g("open_shove@40+") >= 0.10:
        return "jammer (shoves 40bb+ deep)"
    if g("bigcall") >= 0.50 and g("post_vsbet_fold") <= 0.25:
        return "calling station"
    if g("vpip") < 0.20:
        return "nit (VPIP<20%)"
    if g("vpip") >= 0.40 and g("pfr") >= 0.25:
        return "loose-aggressive"
    if g("vpip") >= 0.35 and agg < 0.5:
        return "loose-passive"
    if agg >= 0.5:
        return "tight-aggressive"
    return "other"


def main():
    metas = sorted((json.loads(p.read_text()) for p in BASE.glob("*/meta.json")), key=lambda m: m["created_at"])
    label = {m["round_id"]: f"R{i + 1}" for i, m in enumerate(metas)}
    st = pd.concat(pd.read_csv(BASE / m["round_id"] / "team_stats.csv") for m in metas)
    st = st[st.split == "all"].copy()
    limp = st[st.stat.str.startswith("open_limp@")].groupby(["round_id", "team_id", "team_name"])[["k", "n"]].sum().reset_index()
    st = pd.concat([st, limp.assign(stat="open_limp", split="all")])
    st = st[st.stat.isin(KEY)]
    st["rate"] = np.where(st.n >= MIN_N, st.k / st.n.replace(0, np.nan), np.nan)
    wide = st.pivot_table(index=["round_id", "team_id"], columns="stat", values="rate", aggfunc="first")
    nwide = st.pivot_table(index=["round_id", "team_id"], columns="stat", values="n", aggfunc="first").add_prefix("n_")
    off = pd.concat(pd.read_csv(BASE / m["round_id"] / "official.csv") for m in metas)
    off = off[~off.forfeited].set_index(["round_id", "team_id"])[["team_name", "avg_points", "moe"]]
    wide = off.join(wide, how="inner").join(nwide)
    wide.insert(0, "round", [label[r] for r in wide.index.get_level_values(0)])
    wide["rank"] = wide.groupby(level=0).avg_points.rank(ascending=False, method="min")
    wide["style"] = [style(r) for _, r in wide[KEY].iterrows()]
    OUT.mkdir(parents=True, exist_ok=True)
    wide.reset_index().to_csv(OUT / "teams_wide.csv", index=False)
    wide.reset_index()[["round", "team_id", "team_name", "avg_points", "rank", "style"]].to_csv(OUT / "styles.csv", index=False)

    rows = []
    for r, g in wide.groupby(level=0):
        top = g[g["rank"] <= 10]
        for k in KEY:
            v = g[k].dropna()
            q = v.quantile([.1, .25, .5, .75, .9]).values if len(v) else [np.nan] * 5
            rows.append({"round": label[r], "stat": k, "teams": len(v), "p10": q[0], "p25": q[1], "p50": q[2],
                         "p75": q[3], "p90": q[4], "top10_p50": top[k].median(),
                         "spearman_vs_points": v.corr(g.loc[v.index, "avg_points"], method="spearman") if len(v) > 5 else np.nan})
    fq = pd.DataFrame(rows)
    fq.to_csv(OUT / "field_quantiles.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    print("Rounds: " + ", ".join(f"{label[m['round_id']]}={m['round_id'][:8]} ({m['tables_seen']} tables seen)" for m in metas))
    print("\n## Field distribution per stat (across teams), with top-10 median and correlation with points")
    print(fq.set_index(["stat", "round"]).sort_index(level=0, sort_remaining=False).to_string())

    print("\n## Style mix per round (count of teams)")
    print(pd.crosstab(wide["style"], wide["round"]).to_string())
    print("\n## Style mix of each round's top 10")
    print(pd.crosstab(wide[wide["rank"] <= 10]["style"], wide[wide["rank"] <= 10]["round"]).to_string())
    print("\n## Mean points by style per round")
    print(wide.pivot_table(index="style", columns="round", values="avg_points", aggfunc="mean").to_string())

    s = wide.reset_index().pivot_table(index="team_id", columns="round", values="style", aggfunc="first")
    rounds = sorted(s.columns)
    for a, b in zip(rounds, rounds[1:]):
        both = s[[a, b]].dropna()
        moved = (both[a] != both[b]).sum()
        print(f"\n## Style transitions {a} -> {b}: {moved} of {len(both)} teams changed label")
        print(pd.crosstab(both[a], both[b]).to_string())


if __name__ == "__main__":
    main()
