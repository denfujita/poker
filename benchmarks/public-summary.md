# Basic equity v1 — local benchmarks

These are aggregate **local simulator results**, not live tournament results. Each scenario contains 200 eight-player tables against the supplied reference bots.

| Hero and opponents | Mean points | 95% CI for mean | Outright wins | Wilson 95% CI for win rate | Top-three rank | Failed decisions |
| --- | ---: | --- | ---: | --- | ---: | ---: |
| Basic equity vs mixed defaults | 26.50 | 23.03–29.97 | 106/200 (53.0%) | 46.1%–59.8% | 106/200 | 0/22,221 |
| Original template vs mixed defaults | 12.25 | 10.41–14.09 | 0/200 (0.0%) | 0.0%–1.9% | 96/200 | 0/19,370 |
| Basic equity vs 7 check-or-fold bots | 50.00 | Degenerate; see note | 200/200 (100.0%) | 98.1%–100.0% | 200/200 | 0/43,197 |
| Basic equity vs 7 minimum-raisers | 36.08 | 34.09–38.06 | 89/200 (44.5%) | 37.8%–51.4% | 200/200 | 0/6,433 |

In the matched mixed-field comparison, the strategy gained **14.25 points per table** over the original template (paired normal 95% CI **10.27–18.23**). All 200 pairs matched table index, table seed, and initial entry seating. Later play can differ because decisions differ.

The mixed field contains three check-or-fold bots and four minimum-raisers. The benchmark strategy has one seat. The original-template comparison changes only that hero strategy.

**Passive-field caution:** all 200 observed scores were 50, producing an empirical normal mean interval of [50, 50]. That interval is degenerate and does not establish zero uncertainty. The Wilson interval for its 200/200 win rate is **98.1%–100%**; wins are not guaranteed.

## Finishing positions and run length

| Scenario | Finishing-position counts | Average hands | Tables reaching 250-hand cap |
| --- | --- | ---: | ---: |
| mixed | 1: 106, 5: 90, 6: 4 | 107.69 | 0/200 |
| template-mixed | 2: 53, 3: 43, 4: 57, 5: 47 | 100.47 | 0/200 |
| passive | 1: 200 | 176.05 | 0/200 |
| aggressive | 1: 89, 2: 103, 3: 8 | 5.00 | 0/200 |

Finishing ranks include ties. In particular, several minimum-raisers may bust together and share the payout for the tied places. The mean point totals use the actual scoring function, not a payout reconstructed from the finish histogram.

## Rules and reproducibility

- Variant: `flop_discard_reveal`; eight players; 2,000 starting chips each.
- Blinds begin at 10/20 and advance every 20 hands. The complete schedule is in `public-summary.json`.
- Payouts: 50/30/20 points; 100 total points per table. Hand cap: 250. Remaining stacks receive ICM shares at the cap.
- Decision allowance: 1 ms; time bank: 100 ms; memory limit: 65,536 bytes.
- Four concurrent tables per run. No resampling continuations beyond the original table and no ICM luck correction.

| Scenario | Seed |
| --- | --- |
| mixed | `basic-equity-v1-mixed-batch1` |
| template-mixed | `basic-equity-v1-mixed-batch1` |
| passive | `basic-equity-v1-passive-batch1` |
| aggressive | `basic-equity-v1-aggressive-batch1` |

| Bot | SHA-256 of `agent.py` |
| --- | --- |
| basic_equity_v1 | `61033f38526fcfe6591387efb8f9f376a0d7a3f2fe51c5b6835b1ffd8c69cb7f` |
| check_or_fold | `2914ffface89473f6a1a75ed8a12ec80f0029d26a5411048feb4b967e1c47230` |
| min_raiser | `48f85f7554e3b56abd3ddd4968e28ab92dfe6e89371ed0d7e5842a8b903db369` |
| starter_template | `02468a80cc34cc427a289d61d6833e534831cd1d4da4ad09c619b7e7e635c1b3` |

## Verification and interpretation

All **800 tables** were checked: each contains 100 points and 16,000 final chips in total (floating-point point error below 1e-9). All source summary metrics were independently recomputed from per-table results and matched. The run recorded **0 failed decisions across 534,054 decisions** for all entries.

Intervals use one hero-table observation as the sampling unit, not individual decisions or cloned opponent seats. Mean intervals use a normal approximation; win-rate intervals use Wilson intervals. All intervals are unadjusted 95% intervals.

The default bots are intentionally weak and repetitive. These results measure this fixed test matrix and do not forecast live-tournament placement. Do not combine the scenarios into a single predicted tournament score.

Machine-readable aggregate metrics, including the full rules, paired difference statistics, and interval definitions, are in `public-summary.json`. No local filesystem paths, account identifiers, credentials, or raw hand histories are included.
