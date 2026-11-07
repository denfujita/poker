# Results log

## Practice round 1 (tournament 5da6d631, weight 0, 2026-11-07 02:41 UTC)
Source: `GET /api/tournaments/5da6d631-2bcf-4fe2-9e7a-01b9e8ecac75/results` → `practice-1/results.json`.
1000 tables per team, 8 seats, 92 non-forfeit teams. A bot with no edge averages 100/8 = 12.5 pts/table.

- 3betblind (submission 4048b807, `bots/v1-live` = box `~/work/basic-equity-v1/agent.py`, sha256 61033f38…, 7562 B):
  **4.23 ± 0.77 pts/table, rank 85/92**; 1st 5.5%, 8th 25.0%. 67,354 decisions, 0 missed, 0 restarts.
- Top: TeamBallHog 23.98 ± 1.39, AZ 22.45, sandylikesfrogs 21.77. Median 13.2.
- Hand history download: route not found in the API; not analyzed yet.

## Local diagnosis (kit simulator, macOS, 200 tables unless noted, `--no-history`)
Opponents: `examples/*` from the kit; `bots/tight_jammer` (all-in only with strong hands);
`bots/always_jam` (all-in every time). `bots/v1-nobigcall` = v1-live plus ONE diagnostic rule:
fold a call costing >= 25% of our chips unless equity vs random >= 0.75.

| Field (7 opponents)           | seed | v1-live | v1-nobigcall |
|-------------------------------|------|---------|--------------|
| 7 min_raiser (100 tables)     | s1   | 38.04   | –            |
| 7 check_or_fold (100 tables)  | s1   | 50.00   | –            |
| 7 tight_jammer                | s2   | 4.10    | 24.00        |
| 3 jammer, 2 min_raiser, 2 c/f | s3   | 9.40    | 26.35        |
| 7 always_jam                  | s4   | 31.12   | 36.20        |
| 2 always_jam, 5 tight_jammer  | s5   | 8.20    | 26.20        |

Reading: v1 reproduces its real score only against selective aggression (4.10 vs 4.23 live), and the
gap closes when it stops making big calls. Mechanism: call/raise equity is computed against
uniformly random hands, so every bet and every all-in is treated as if made with a random hand.
Same seed does not mean identical deals once actions differ; rough SE per cell ≈ ±1.3 pts.

Reproduce, from `starter-kit/`:
`.venv/bin/poker-agent play ../bots/v1-live ../bots/tight_jammer (x7) --tables 200 --seed s2 --no-history`

## Practice round 2 (tournament af2a0969, weight 0, 2500 tables, 116 non-forfeit teams)
Official: TeamBallHog 23.46 ± 0.87, AZ 22.56, pocket rockets 21.39, Always Folds 20.60, 2 Curry 20.57.
3betblind 3.70 ± 0.45, rank 110/116 (same submission 4048b807). 161,678 decisions, 0 missed.

## Hand-history profiling (both practice rounds)
Pipeline: `analysis/extract.py data/raw/hands-<id>.jsonl.gz` → `data/derived/<id>/{actions,showdowns,seats}.csv`;
`analysis/profile.py data/derived/<id>` → `results/<round>/profile.txt`.
Caveats: only tables our bot sat at (our bot donates chips, so per-team points there run high);
showdown stats only cover hands that reached showdown; shown cards are the 2 retained, not the 3 dealt.
Key round-2 numbers are in the conversation write-up and in `round-af2a0969/profile.txt`.
