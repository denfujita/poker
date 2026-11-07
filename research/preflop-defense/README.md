# Separate preflop defense experiments

These are **research candidates, not active submissions**. Both start independently
from frozen active v8, commit `513de720a415e50cd86a13403e5fb6ed11401905`, source
`ab7fa0462a7d2b783c7bd90ad6b3f7fab53c1914b1ac2a3ee76cd1053484abbc`.
Neither includes candidate A's wider call-eligibility gate. The repository root
remains candidate A; no main-branch promotion or tournament upload is implied.

## Shared experimental domain

The test applies only to a hand in the existing top 2.5% ordinal ranking, at an
eight-player table, facing one opponent's first open of 2–3 BB, with at least
50 BB effective against that opener. Antes, limps, calls, all-in opponents, and
calls that exhaust hero's stack are excluded. Existing behavior is retained outside
this domain, including the v8 postflop policy and terminal point-value call veto.

The percentile ordering and thresholds are heuristics for this variant, not a GTO
solution. The inherited preflop model approximates the three-card discard game.

## Candidate B: premium sampling

[`variants/premium-64-b`](variants/premium-64-b/) retains v8's policy but increases
the equity sample count from 16–24 to **64** in the experimental domain. It changes
numerical precision rather than the ordinal gates or an opponent's response model.
It still assumes all currently active opponents participate in its sampled showdown.

Agent SHA-256:
`2f5a92866b3aebde2a1a8094613592c781bd8ab1ad7901dda7b4298a945da69a`.

## Candidate C: premium value 3-bet

[`variants/premium-threebet-c`](variants/premium-threebet-c/) proposes a legal,
non-all-in 3-bet in the experimental domain: **3× the open in position, 4× out of
position**. It does not widen the existing top-2.5% eligibility. The proposal precedes
the inherited sampled-showdown branch and must be below both players' effective
total stacks. If the size is unavailable, v8's ordinary decision path remains.

This is a deliberately testable policy override, not evidence that each proposed
raise has positive EV or that the assumed opponent fold response is calibrated.

Agent SHA-256:
`350d84aa0dd4270b7176a2833501dceddd67f86817a5a192a395609ca9fac620`.

## Focused verification and status

The shared public checker passes **516 assertions across 248 generated engine
states**, including ten natural premium-hand routes. It verifies sampling dispatch,
raise sizing and legality, exclusions, malformed memory, unchanged out-of-scope
behavior, and the normal `Agent.act` entry point. Both source files pass the official
static checker.

These focused results were recorded by the variant author. Publication independently
verified the frozen source hashes and diffs; its repeat run stopped at a local
dependency-file I/O stall and is not counted as an additional passing check.

Initial generic-field comparisons do not establish an improvement. Further matched
Round-4-style proxy testing and runtime validation are separate pending gates.
Do not treat focused correctness checks as a tournament-strength result.

Reproduce using the official Python 3.12 kit environment:

```sh
mkdir -p .local/v8-baseline
git show 513de720:agent.py > .local/v8-baseline/agent.py
git show 513de720:point_value.py > .local/v8-baseline/point_value.py
git show 513de720:preflop_policy.json > .local/v8-baseline/preflop_policy.json
"$POKER_PY" tools/check_preflop_premium_variants.py \
  .local/v8-baseline/agent.py \
  research/preflop-defense/variants/premium-64-b/agent.py \
  research/preflop-defense/variants/premium-threebet-c/agent.py
"$POKER_KIT/.venv/bin/poker-agent" check research/preflop-defense/variants/premium-64-b/agent.py
"$POKER_KIT/.venv/bin/poker-agent" check research/preflop-defense/variants/premium-threebet-c/agent.py
```

Each variant folder contains the three runtime files and a checksum manifest.
`point_value.py` (`6bbe4e22…`) and `preflop_policy.json` (`8f7f0a9c…`) are unchanged
from active v8. Package only the runtime files together after complete validation.
Private histories, account metadata, and raw per-table outputs are excluded.
