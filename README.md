# Tight context-aware poker bot

A chip-EV strategy for the NO LIMIT Bay Area flop-discard-and-reveal variant. The current source is **tight v4**, SHA-256 `47f1af369299958021af7a76b05940b5cbfbf935e9c1ebae7e823dc3f4cb8a33`.

**Upload a ZIP containing both `agent.py` and `preflop_policy.json` at its root.** The bot loads the JSON at import time; uploading `agent.py` alone will fail. The `tools/` scripts are development utilities, not submission files.

## Strategy

- Use three-card strength percentiles for position- and stack-dependent preflop openings. Defensive hands must pass an ordinal strength gate and a simulated-equity/pot-odds check; weak calls cannot fall through into a generic reraise.
- Handle heads-up positions, busted-seat gaps, limpers, current blinds, short stacks, and all-in prices explicitly. Keep inexpensive short-stack continuations available.
- Compare all three retained pairs after the flop using shared simulated runouts. Break exact equity ties by current made-hand strength; a strictly higher-equity draw stays primary. Expose the retained card less connected to the board, as an information heuristic.
- Sample 16–24 possible showdowns. Fix each live opponent's exposed card in its hand and remove every known public card, including folded players' exposed cards, plus the bot's own discard from the remaining deck.
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
"$POKER_KIT/.venv/bin/poker-agent" pack .local/bot reports/tight-v4.zip
"$POKER_KIT/.venv/bin/poker-agent" check reports/tight-v4.zip
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

## Recorded benchmark results (historical v1)

These results measure the original v1 source (SHA-256 `61033f38526fcfe6591387efb8f9f376a0d7a3f2fe51c5b6835b1ffd8c69cb7f`), before exposed-card conditioning. They are not measurements of the current tight v4 source. See [v4 validation](validation/v4.md) for its correctness and runtime checks, [v3 validation](validation/v3.md) for the earlier action model, and [v2 validation](validation/v2.md) for exposed-card conditioning.

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
