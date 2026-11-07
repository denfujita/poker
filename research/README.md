# research/ — Yifan's analysis (branch yifan/preflop-jamfold)

- `analysis/` hand-history extraction (`extract.py`) and team profiling (`profile.py`); true 3-card preflop
  equity (`preflop_equity.py`); 40-bucket equity matrix (`bucket_matrix.py`); jam/fold equilibrium solver (`jamfold.py`)
- `bots/preflop_tables/` runtime tables: `pct_by_combo.json` (strength percentile per 3-card combo, 0 = best)
  and `preflop.json` (jam/call share by players/position/stack). Lookup 0.2 us, load 4 ms.
- `bots/` test opponents (`tight_jammer`, `always_jam`), `v1-live` copy of submission 4048b807, `v1-nobigcall` diagnostic
- `results/` round results, local diagnosis, team profiles; see `results/README.md`
- `bench/` decision-budget and blocker benchmarks

Raw/derived hand histories (`research/data/`) are not committed. Rebuild from `research/` with the kit venv:
`python analysis/extract.py data/raw/hands-<id>.jsonl.gz`, `python analysis/preflop_equity.py --trials 3000 --opps 1 3 7`,
`python analysis/bucket_matrix.py --k 40 --trials 20000`, `python analysis/jamfold.py --k 40 --iters 4000`.
