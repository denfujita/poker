# Exact river side-pot candidate

Source SHA-256: `2fe4de9a0d6f35fc5c3bb0aaccf47699e81e0eef2346662ac825d2f67e0f19d5`. Policy asset remains `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

The small Monte Carlo sample in practice v5 can misprice river side pots. This candidate removes sampling error for a specific tractable case: two opponents, each with one known exposed card and one hidden card, a complete five-card board, and a requested side-pot contender group. Ordinary single-pot requests and unsupported states keep the sampled path.

For each opponent, the calculation evaluates every available hidden card and its existing action-likelihood weight. Products of weighted below/tied/above-hero totals give the joint result; subtracting same-card collisions enforces sampling without replacement. Single-opponent side pots still integrate the excluded opponent's blocker and likelihood effects. All pot groups share the same joint distribution, and ties use each group's actual eligible-player count.

This takes linear work in the remaining deck rather than enumerating all ordered pairs. It is exact **within the existing heuristic range model**, not a calibrated opponent posterior or a full-game GTO solution.

## Evidence and status

- `tools/check_exact_river.py` passes 150 assertions across 30 generated joint cases against an independent ordered-pair oracle. Cases include weighted ranges, public and discarded blockers, ties, different contender groups, and preservation of the ordinary sampled path.
- Independent reviews passed 405 and 124 checks. Two previously identified false-positive calls become folds under the corrected calculation.
- The existing 21-check side-pot suite (including baseline reproduction) passes.
- Remote safety/runtime checks and final deployment approval are pending. This branch is a candidate; main and the active practice bundle remain source `b208a897…`.

Run with the official kit environment:

```sh
python tools/check_exact_river.py agent.py
python tools/check_side_pots.py agent.py --baseline /path/to/tight-v4/agent.py
```

The public benchmark reports describe earlier versions. No field-strength gain is inferred from these mathematical regression tests.
