# Exact river side-pot evaluation (v6)

Source SHA-256: `2fe4de9a0d6f35fc5c3bb0aaccf47699e81e0eef2346662ac825d2f67e0f19d5`. Policy asset remains `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

The small Monte Carlo sample in practice v5 can misprice river side pots. V6 removes sampling error for a specific tractable case: two opponents, each with one known exposed card and one hidden card, a complete five-card board, and a requested side-pot contender group. Ordinary single-pot requests and unsupported states keep the sampled path.

For each opponent, the calculation evaluates every available hidden card and its existing action-likelihood weight. Products of weighted below/tied/above-hero totals give the joint result; subtracting same-card collisions enforces sampling without replacement. Single-opponent side pots still integrate the excluded opponent's blocker and likelihood effects. All pot groups share the same joint distribution, and ties use each group's actual eligible-player count.

This takes linear work in the remaining deck rather than enumerating all ordered pairs. It is exact **within the existing heuristic range model**, not a calibrated opponent posterior or a full-game GTO solution.

## Evidence and status

- `tools/check_exact_river.py` passes 150 assertions across 30 generated joint cases against an independent ordered-pair oracle. Cases include weighted ranges, public and discarded blockers, ties, different contender groups, and preservation of the ordinary sampled path.
- Independent reviews passed 405 and 124 checks. Two previously identified false-positive calls become folds under the corrected calculation.
- The existing 21-check side-pot suite (including baseline reproduction) passes.
- Remote submission checks, 342 legality states, 90 malformed-memory cases, and a zero-bank probe (0/100 failed decisions) passed. The required 200-table reference match averaged 43.35 points, with 154 wins and zero failed decisions across all bots. The uploaded two-file bundle reached ready/active status.
- The exact branch's 960 timed calls had p99 0.479 ms and maximum 0.520 ms. A separate isolated selection stress pass had one 2.04 ms outlier in 480 calls; an interleaved 480-call-per-version comparison had maxima of 0.430 ms for v5 and 0.440 ms for v6, with no calls over 1 ms. These measurements do not establish a hard bound or explain the isolated outlier. See [full validation scope](../validation/v6.md).

Run with the official kit environment:

```sh
python tools/check_exact_river.py agent.py
python tools/check_side_pots.py agent.py --baseline /path/to/tight-v4/agent.py
```

In 200 matched pairs against a fixed field of seven tight-v4 opponents, v6 averaged 14.70 points versus 14.60 for v5. Only one score changed (+20); the paired 95% t interval for the +0.10 mean difference spans −0.097 to +0.297. This does not establish stronger play. See the [v6 aggregate report](../benchmarks/exact-river-v6-validation.md). Mathematical correctness and reference-bot results also do not establish improved tournament-field strength.
