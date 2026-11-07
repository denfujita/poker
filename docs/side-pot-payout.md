# Side-pot payout correction (practice v5)

Source SHA-256: `b208a8970bfc314471e07efe1279815704749e2c4c2270b707be9b39b698d7de`. The required policy JSON remains `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

The previous tight-v4 baseline applies one equity against all live opponents to the full eligible pot. With unequal all-in stacks, a player can lose the main pot and still win a profitable side pot. Practice v5 instead evaluates each pot against only the opponents eligible for it.

## Regression and behavior

A synthetic river state has a 300-chip main pot and a possible 1,800-chip side pot after the hero calls 900. A short all-in player has an exposed unbeatable card, but the hero is guaranteed to beat the deep opponent. The baseline folds because its all-opponent equity is zero; practice v5 calls because the side-pot return gives +900 chips of incremental EV.

The implementation retains folded players' chips, caps hero eligibility, separates certain unmatched returns from contested money, and reconstructs silent prior-street refunds. Active opponents remain eligible up to their available stacks without inventing unmade call chips. Projected raises get their own layers and payout estimate. Every layer uses the same sampled world and one retained pair; it cannot pick a different pair for each pot.

## Verification and limits

- `tools/check_side_pots.py` passes 20 candidate checks, or 21 with `--baseline` to reproduce the former fold. Cases cover layer eligibility, ties, folded money, short-stack caps, refunds, pending callers, selection consistency, and projected raises through synthetic SDK states.
- An independent math audit passed 23 checks, and an 800-state replay passed. Existing discard, preflop, and range regression suites also passed.
- The required 200-table reference match completed at 42.60 mean points with zero failures. The 200-pair comparison against seven v4 copies returned 14.60 versus 14.15 points, with only four scores changed and zero failures in either field. This is limited fixed-field evidence, not a tournament-strength claim; see the [full aggregate report](../benchmarks/sidepot-v5-vs-v4.md).
- Eight-player stress timing stayed below 1 ms, while additional ten-player stress had three calls over 1 ms in 960 measurements. The report preserves these tail-latency limits.

Run with the official kit environment and keep the policy sidecar beside each source:

```sh
python tools/check_side_pots.py agent.py --baseline /path/to/tight-v4/agent.py
```

This practice version contains the side-pot correction only; the restricted jam/fold experiment remains separate. Its small Monte Carlo sample can give noisy river side-pot estimates. Exact river evaluation is a separate follow-up and is not included in this source.
