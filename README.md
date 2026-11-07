# Exact heads-up river candidate

This isolated heads-up river candidate, SHA-256 `38ed571635c946ccd65ece23893f37b6a27cd72fb82e1d8a36805ac06dc96112`, is based on frozen v6 (`2fe4de9a…`). It enumerates the one unknown opponent card on supported heads-up river states using the existing weights and blockers; other strategy and sampling domains are unchanged. Completed validation passed, but the 200-pair benchmark measured **14.25 versus 14.40 points** (paired change **−0.15**, 95% interval **−0.959 to +0.659**), with no demonstrated points gain. See [scope and verification](docs/exact-heads-up-river.md) and the [final validation report](validation/heads-up-river-candidate.md). The integration owner controls the combined bot, main promotion, and upload; this branch is an isolated patch, not a replacement for newer combined sources.

The v6 exact calculation is retained for river side pots with exactly two opponents and one exposed/one hidden card each. It integrates the existing joint weighted model over all legal hidden-card pairs in O(deck size). States outside either exact calculation retain the sampled path. See [scope and tests](docs/exact-river-side-pots.md).

The correction estimates each pot against its eligible opponents, preserving folded contributions and unmatched returns. See [the correction and regression case](docs/side-pot-payout.md).

**Upload a ZIP containing both `agent.py` and `preflop_policy.json` at its root.** The bot loads the JSON at import time; uploading `agent.py` alone will fail. The `tools/` scripts are development utilities, not submission files.

## Baseline strategy and payout correction

- Use three-card strength percentiles for position- and stack-dependent preflop openings. Defensive hands must pass an ordinal strength gate and a simulated-equity/pot-odds check; weak calls cannot fall through into a generic reraise.
- Handle heads-up positions, busted-seat gaps, limpers, current blinds, short stacks, and all-in prices explicitly. Keep inexpensive short-stack continuations available.
- Compare all three retained pairs after the flop using shared simulated runouts. Break exact equity ties by current made-hand strength; a strictly higher-equity draw stays primary. Expose the retained card less connected to the board, as an information heuristic.
- Build separate pot layers for capped all-in opponents. Estimate each layer from the same sampled worlds, use one retained pair across all layers, and recompute projected raise payouts.
- Integrate supported heads-up river hands and two-opponent river side pots exactly; otherwise sample 16–24 possible showdowns. Fix each live opponent's exposed card in its hand and remove every known public card, including folded players' exposed cards, plus the bot's own discard from the remaining deck.
- Weight opponent hands using public calls/raises and historical bet sizes. Add caution under large bets, reraises, and repeated barrels; apply a separate gate to weak reraises. Value-raise sizing uses 62% of the pot after calling, subject to legal and stack limits.

The percentile ordering comes from the reviewed teammate asset; **its full jam/call bucket arrays are bundled but unused**. Opening and defense thresholds are heuristics, not the solver's policy, GTO, or ICM. Action likelihoods are also uncalibrated, and the small sample budget can give noisy estimates. The raise model assumes opponents continue and assigns no fold equity. There is no learning across tables.

## Setup

Use **Python 3.12** and the official starter kit for the Bay Area variant. Obtain that kit from the [tournament site](https://pokerbot.sequoiacap.com/tournament); the competition SDK and engine are not redistributed in this repository.

From this repository, set the kit path and install its exact requirements and SDK:

```sh
export POKER_KIT=/absolute/path/to/starter-kit
python3.12 -m venv "$POKER_KIT/.venv"
"$POKER_KIT/.venv/bin/python" -m pip install -r "$POKER_KIT/requirements.txt"
"$POKER_KIT/.venv/bin/python" -m pip install \
  "$POKER_KIT/sdk/agent-protocol" \
  "$POKER_KIT/sdk/engine" \
  "$POKER_KIT/sdk/agent-sdk"
export POKER_PY="$POKER_KIT/.venv/bin/python"
mkdir -p reports
```

On macOS, the kit's LightGBM/XGBoost dependencies may also require the OpenMP runtime (`brew install libomp`). Ordinary SDK installs are shown above; after editing SDK source, reinstall those packages.

## Validate

```sh
"$POKER_KIT/.venv/bin/poker-agent" check agent.py
"$POKER_PY" tools/validate_strategy.py agent.py \
  --fixtures-out reports/fixtures.json --repeats 10 \
  --report reports/validation.json
"$POKER_PY" tools/check_equity_invariants.py agent.py \
  --fixtures-in reports/fixtures.json --report reports/equity-invariants.json
"$POKER_PY" tools/check_discard.py agent.py
"$POKER_PY" tools/check_range_model.py agent.py
"$POKER_PY" tools/check_integrated_preflop.py agent.py
"$POKER_PY" tools/check_side_pots.py agent.py
"$POKER_PY" tools/check_exact_river.py agent.py
"$POKER_PY" tools/check_heads_up_river.py agent.py
"$POKER_PY" tools/no_bank_check.py . "$POKER_KIT/examples/check_or_fold" \
  --tables 10 --hand-cap 20 --report reports/no-bank.json
"$POKER_KIT/.venv/bin/poker-agent" play . \
  "$POKER_KIT/examples/check_or_fold" "$POKER_KIT/examples/min_raiser" \
  --tables 200 --seed basic-equity-v1-validation --no-history
```

The validation harness generates real-engine states spanning 2, 3, 8, and 10 players; selection, all betting streets, short calls, and all-in selections. The no-bank probe uses the normal guest process protocol with a 1 ms decision allowance and zero time bank. Its local result does not replace the server's upload validation.

## Package the submission

Stage only the two runtime files, then run the kit packer and checker:

```sh
mkdir -p .local/bot reports
cp agent.py preflop_policy.json .local/bot/
"$POKER_KIT/.venv/bin/poker-agent" pack .local/bot reports/exact-hu-river-candidate.zip
"$POKER_KIT/.venv/bin/poker-agent" check reports/exact-hu-river-candidate.zip
```

Both files must remain together for local tests and production. The JSON asset's SHA-256 is `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

## Benchmark eight-player tables

```sh
"$POKER_PY" tools/benchmark.py . \
  "$POKER_KIT/examples/min_raiser" "$POKER_KIT/examples/check_or_fold" \
  "$POKER_KIT/examples/min_raiser" "$POKER_KIT/examples/check_or_fold" \
  "$POKER_KIT/examples/min_raiser" "$POKER_KIT/examples/check_or_fold" \
  "$POKER_KIT/examples/min_raiser" \
  --tables 200 --seed basic-equity-v1-mixed-batch1 --concurrency 4 \
  --out reports/mixed.jsonl --summary reports/mixed-summary.json
```

Use the same seed and opponent ordering to compare versions, then calculate uncertainty from paired per-table differences. Use a new seed block for additional independent evidence. The runner records actual ICM-aware table points, finishing ranks, decisions, failures, hand-cap frequency, and uncertainty intervals. A rank at the hand cap is not necessarily an outright win; top-three rank is not necessarily a cash rate.

Default bots are intentionally weak. Scores against them are diagnostic benchmarks, not a forecast of performance against the tournament field.

## Historical v6 paired comparison

These results apply to v6, not this candidate. Across **200 matched pairs** against a fixed field of seven tight-v4 bots, v6 averaged **14.70 points** versus **14.60** for sampled-side-pot v5. Only **one score changed** (+20); the paired mean difference was **+0.10 points/table**, with a 95% t interval of **−0.097 to +0.297**. This comparison does not establish stronger play. Both versions had zero failed decisions in the benchmark.

See the [v6 validation and aggregate report](benchmarks/exact-river-v6-validation.md) and [JSON](benchmarks/exact-river-v6-validation.json) for exact source hashes, matched seeds, settings, failures, and timing limitations. The reference-bot match and mathematical regressions establish specific checks, not tournament-field performance.

## Historical practice v5 paired comparison

These results measure sampled-side-pot v5, not v6. Across **200 matched pairs** against seven copies of tight v4, practice v5 averaged **14.60 points** versus **14.15** for the control. Only **four paired scores changed** (+20, +20, +20, +30); the mean difference of **+0.45** is limited evidence in this fixed field. The exact two-sided sign-flip test gives p = 0.125, so this does not establish a robust improvement.

The required 200-table reference match averaged **42.60 points**, with zero failed decisions across all bots. Normal eight-player matches also had zero failures. Additional ten-player stress timing had three calls over 1 ms in 960 measurements, so a universal sub-millisecond claim is not supported. See the [v5 aggregate report](benchmarks/sidepot-v5-vs-v4.md) and [JSON](benchmarks/sidepot-v5-vs-v4.json) for exact versions, settings, intervals, and runtime limits.

## Baseline tight v4 paired comparison

These results apply to frozen tight v4, not practice v5 or v6. Across **200 matched pairs of eight-player tables** against seven v3 opponents, tight v4 averaged **23.5 points** versus **13.9** for the v3 control. The paired gain was **+9.6 points/table** (95% Student-t interval **+6.30 to +12.90**). Both fixed seed batches favored v4, with zero failed decisions in either field.

Top-three finishes rose from 79 to 158 of 200, while outright wins fell from 33 to 25. This is evidence about one fixed local v3 field, not the tournament field. See the [paired report](benchmarks/tight-v4-vs-v3.md) and [aggregate JSON](benchmarks/tight-v4-vs-v3.json) for seeds, exact source hashes, finish counts, and uncertainty details.

## Recorded benchmark results (historical v1)

These results measure the original v1 source (SHA-256 `61033f38526fcfe6591387efb8f9f376a0d7a3f2fe51c5b6835b1ffd8c69cb7f`), before exposed-card conditioning. They are not measurements of v6, practice v5, or frozen tight v4. See [v6 validation](validation/v6.md), [practice v5 status](validation/v5.md) and [v4 validation](validation/v4.md) for version-specific evidence, [v3 validation](validation/v3.md) for the earlier action model, and [v2 validation](validation/v2.md) for exposed-card conditioning.

The initial batch ran 200 eight-player tables per scenario, with the same mixed-field seeds and seating used for the original-template comparison:

| Hero and opponents | Mean points per table | Outright wins |
| --- | ---: | ---: |
| Basic equity vs mixed defaults | 26.50 | 53.0% |
| Original template vs mixed defaults | 12.25 | 0.0% |
| Basic equity vs seven check-or-fold bots | 50.00 | 100.0% |
| Basic equity vs seven minimum-raisers | 36.08 | 44.5% |

The paired mixed-field improvement was **14.25 points per table** (95% confidence interval **10.27–18.23**). All 800 tables completed with zero failed decisions across all entries. These results apply to the fixed reference-bot fields; a 200/200 observed win rate is not a guarantee.

See [the aggregate report](benchmarks/public-summary.md) for confidence intervals, finishing positions, seeds, rules, hashes, and interpretation limits. [Machine-readable aggregate results](benchmarks/public-summary.json) are also included; raw tables and hand histories are not.

## Research reviews

The [preflop jam/fold review](docs/preflop-jamfold-review.md) records the inspected branch snapshot, model assumptions, missing policy exports, and checks needed before integrating that research. Tight v4 uses the reviewed three-card percentile ordering with an explicitly heuristic policy; the solver jam/call arrays remain unused.

## Data handling

Only code, tests, and sanitized aggregate results belong in this repository. Keep credentials, API responses containing account details, private hand histories, raw per-table outputs, and local environment files untracked. The supplied `.gitignore` covers the usual generated locations.
