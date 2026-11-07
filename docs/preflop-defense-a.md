# Affordable heads-up 3-bet defense experiment

Candidate A changes only one preflop eligibility cutoff. The frozen v8 baseline
rejects nonblind hands outside its top 4% after a second raise before calculating
equity. Candidate A widens that cutoff to 8% only when all of these conditions hold:

- Eight players remain in the tournament, with at least 50 BB effective against the raiser.
- Hero opened to 2–3 BB, one opponent reraised, and every other player folded.
- Both remaining players are active; the call does not consume hero's stack.
- No ante, limp, or call appears in the hand.
- The opponent's raise total is at most 12 BB, and the remaining call costs at most 8 BB.

Passing the wider gate still requires the existing equity and call-price test.
The change cannot create a new 4-bet; the existing reraise threshold is unchanged.
The v8 ICM call veto, postflop strategy, and short-stack policies are preserved.

This is a heuristic experiment. Neither the percentile thresholds nor the equity
model are a GTO solution. The inherited estimator has a small sample budget and
approximates the three-card preflop game. Test results below establish the intended
scope and legality, not a measured tournament-point advantage.

## Frozen versions

| Runtime file | Baseline SHA-256 | Candidate SHA-256 |
| --- | --- | --- |
| agent.py | `ab7fa0462a7d2b783c7bd90ad6b3f7fab53c1914b1ac2a3ee76cd1053484abbc` | `a5f142c613f82d6e7aca11b52aa1e7e0bcbfb3b7c4a5f0914383f74b68c21cc0` |
| point_value.py | `6bbe4e226c71d77c1101b6348b1f8372c702eb61136c0fd7436ba7433848597c` | unchanged |
| preflop_policy.json | `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98` | unchanged |

Baseline commit: `513de720a415e50cd86a13403e5fb6ed11401905`.
All three runtime files must be packaged together. Development tools are not runtime files.

## Focused validation

`tools/check_preflop_defense.py` generates states through the official engine, then
checks both `preflop_action` and the normal `Agent.act` entry point. It uses no
private histories. Results: **264 assertions, 168 real-engine states, seven normal
fold-to-call changes, zero failed assertions**.

The exclusions cover shallow stacks, large opens, large reraises, all-ins, fewer
players, antes, and calls. A chip-neutral prize event cannot hide an otherwise
supported sequence. Calls still need sufficient modeled equity and must be legal.

Reproduce in the official Python 3.12 kit environment:

```sh
mkdir -p .local/v8-baseline
git show 513de720:agent.py > .local/v8-baseline/agent.py
git show 513de720:point_value.py > .local/v8-baseline/point_value.py
git show 513de720:preflop_policy.json > .local/v8-baseline/preflop_policy.json
"$POKER_PY" tools/check_preflop_defense.py .local/v8-baseline/agent.py agent.py
```

Matched simulations, runtime validation, and any promotion decision are separate
gates. At publication of this experiment, those simulations are pending and no
new tournament upload has been made from this branch. Raw private histories and
per-table data stay outside this repository.
