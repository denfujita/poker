# Basic equity poker bot

A small Monte Carlo equity and pot-odds baseline for the NO LIMIT Bay Area flop-discard-and-reveal variant. The submitted bot is the single file `agent.py`; the `tools/` scripts are local development utilities and must not be included in a bot upload.

## Strategy

- Start with three private cards. After the flop, compare all three possible retained pairs using shared simulated runouts and keep the pair with the highest average equity.
- Expose the lower-ranked retained card as a simple information heuristic.
- Sample 32–48 possible showdowns against the active/all-in opponents, splitting tied pots correctly and excluding all known own cards, including the discard.
- Use estimated chip EV for calls, free checks, and one legal half-pot value-raise size. Calls are capped by the stack and eligible pots account for short stacks.
- Apply a modest caution margin after repeated current-street raises or large bets. State is local to a decision; the bot does not learn across tables.

This is a deliberately simple chip-EV heuristic, not a GTO or ICM solution. Opponents are modeled as random two-card hands; their exposed cards, discard skill, and inferred ranges are not used. The raise model assumes live opponents continue and assigns no fold equity. Preflop it estimates the best fixed retained pair rather than valuing every later selection opportunity.

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
"$POKER_PY" tools/no_bank_check.py . "$POKER_KIT/examples/check_or_fold" \
  --tables 10 --hand-cap 20 --report reports/no-bank.json
"$POKER_KIT/.venv/bin/poker-agent" play . \
  "$POKER_KIT/examples/check_or_fold" "$POKER_KIT/examples/min_raiser" \
  --tables 200 --seed basic-equity-v1-validation --no-history
```

The validation harness generates real-engine states spanning 2, 3, 8, and 10 players; selection, all betting streets, short calls, and all-in selections. The no-bank probe uses the normal guest process protocol with a 1 ms decision allowance and zero time bank. Its local result does not replace the server's upload validation.

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

## Recorded benchmark results

The initial batch ran 200 eight-player tables per scenario, with the same mixed-field seeds and seating used for the original-template comparison:

| Hero and opponents | Mean points per table | Outright wins |
| --- | ---: | ---: |
| Basic equity vs mixed defaults | 26.50 | 53.0% |
| Original template vs mixed defaults | 12.25 | 0.0% |
| Basic equity vs seven check-or-fold bots | 50.00 | 100.0% |
| Basic equity vs seven minimum-raisers | 36.08 | 44.5% |

The paired mixed-field improvement was **14.25 points per table** (95% confidence interval **10.27–18.23**). All 800 tables completed with zero failed decisions across all entries. These results apply to the fixed reference-bot fields; a 200/200 observed win rate is not a guarantee.

See [the aggregate report](benchmarks/public-summary.md) for confidence intervals, finishing positions, seeds, rules, hashes, and interpretation limits. [Machine-readable aggregate results](benchmarks/public-summary.json) are also included; raw tables and hand histories are not.

## Data handling

Only code, tests, and sanitized aggregate results belong in this repository. Keep credentials, API responses containing account details, private hand histories, raw per-table outputs, and local environment files untracked. The supplied `.gitignore` covers the usual generated locations.
