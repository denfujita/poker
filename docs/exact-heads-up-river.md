# Exact heads-up river candidate

Source SHA-256: `38ed571635c946ccd65ece23893f37b6a27cd72fb82e1d8a36805ac06dc96112`.
Required policy JSON SHA-256: `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

V6 still samples 24 possible showdowns when exactly one live opponent remains on the river. With that opponent's exposed card fixed, only one card is unknown. Sampling can alter a call/fold decision near its EV threshold even though enumeration is inexpensive.

This candidate enumerates every legal hidden card when the board has five cards, the hero has two retained cards, and the sole live opponent has exactly one exposed card. It preserves the existing action-likelihood model, removes the same own/discarded/public cards from the deck, and divides weighted wins plus half of weighted ties by total weight. Eligible pot groups share that result; empty contender groups remain certain returns. Other game states and strategy thresholds are unchanged.

The result is exact within the existing heuristic range model. It does not calibrate that model, add opponent learning, or solve GTO play.

## Evidence and status

- `tools/check_heads_up_river.py` passes 335 assertions with a frozen v6 baseline, or 174 without it. Its 58 synthetic equity cases cover weights, ties, blockers, and group shape; the baseline run reproduces sampling error and checks 80 excluded-domain cases in ordinary and grouped modes.
- The final independent oracle/replay review verified 961 comparisons and all 84 expected action changes across 901 causal heads-up states. Forty two-opponent states and 682 additional out-of-scope states remained unchanged. Private cards and replay fixtures are not published.
- The package checker, 342 legal-action checks, 90 malformed-memory checks, and the zero-bank probe (0/100 candidate failures) passed. The required 200-table reference match averaged 42.75 points with zero failed decisions.
- In 200 matched pairs against seven frozen v6 opponents, this candidate averaged 14.25 points versus 14.40 for v6: **−0.15 points**, approximate paired 95% t interval **[−0.959, +0.659]**. Ten scores changed and the two seeds disagreed in direction. No tournament-point improvement is demonstrated.
- Both heroes had zero failures (candidate 0/28,099 decisions). Opponents had five failures across four paired tables; all four hero-score deltas were zero. The sensitivity analysis excluding them gave −0.153 points over 196 pairs. The primary result retains all 200 preselected pairs.
- The exact heads-up branch's 960 timed calls had p99 0.287 ms and maximum 0.429 ms. One first-run normal turn call reached 1.097 ms; its repeat stayed below 0.803 ms. These direct timings exclude host/wire overhead and establish no strict 1 ms bound.

The [final sanitized report](../validation/heads-up-river-candidate.md) and [JSON](../validation/heads-up-river-candidate.json) pin the sources, settings, seeds, counts, and limits. The integration owner controls the combined source, final main promotion, and tournament upload. Apply only the narrow source/test patch; do not overwrite a newer combined bot. A changed integration base requires fresh validation.

Run with the official kit environment and keep each source's policy sidecar alongside it:

```sh
python tools/check_heads_up_river.py agent.py --baseline /path/to/frozen-v6/agent.py
```

Earlier public benchmark reports apply to their named source hashes. Only the final heads-up candidate report above measures this frozen source.
