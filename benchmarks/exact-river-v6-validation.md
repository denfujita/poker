# Exact-river v6 validation

The correctness checks passed. The completed matched comparison does **not** establish improved strength: v6 averaged **14.70 points/table** versus **14.60** for sidepot v5, a difference of **+0.10** over 200 matched tables. The approximate paired Student-t 95% interval is **[-0.0972, +0.2972]**. Only one table score changed, by +20 points; the other 199 scores were unchanged.

## Versions and reproducibility

| Component | SHA-256 |
| --- | --- |
| Exact-river v6 `agent.py` | `2fe4de9a0d6f35fc5c3bb0aaccf47699e81e0eef2346662ac825d2f67e0f19d5` |
| Sidepot v5 baseline `agent.py` | `b208a8970bfc314471e07efe1279815704749e2c4c2270b707be9b39b698d7de` |
| Seven v4 opponent copies | `47f1af369299958021af7a76b05940b5cbfbf935e9c1ebae7e823dc3f4cb8a33` |
| Unchanged `preflop_policy.json` | `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98` |
| Checked candidate bundle | `8ed98ab3044dbd5c17a367350ebbb4082cd09f919fdcea5588c0d30654a9a2a1` |

Both versions faced the same seven v4 opponents with matched deal seeds and initial seats. The two batches used `mixed-jam-v5-strong-a` and `mixed-jam-v5-strong-b`, 100 tables each. Source files remained unchanged during the candidate runs. Scores use authoritative final points; they are not reconstructed from finishing positions.

The normal engine used `flop_discard_reveal`, eight players, 2,000 starting chips, no antes, 20 hands per blind level, a 250-hand cap, fixed 50/30/20 payouts, 1 ms decisions and a 100 ms table bank. The blind schedule was 10/20, 20/40, 30/60, 50/100, 80/160, 125/250, 200/400, 300/600, 500/1,000, 800/1,600, 1,200/2,400 and 2,000/4,000. Memory was 65,536 bytes; concurrency was two, with one resampling continuation and no ICM luck correction. The JSON records the full settings.

## Matched results

| Metric | Exact-river v6 | Sidepot v5 |
| --- | ---: | ---: |
| Tables | 200 | 200 |
| Mean points | 14.70 | 14.60 |
| First-place finishes | 25 (12.5%) | 25 (12.5%) |
| Top-three finishes | 91 (45.5%) | 90 (45.0%) |
| Finishes, 1st through 8th | 25, 37, 29, 19, 24, 20, 19, 27 | 25, 37, 28, 19, 24, 20, 20, 27 |
| Candidate failed decisions / decisions | 0 / 29,211 | 0 / 29,084 |
| Whole-field failed decisions / decisions | 0 / 222,206 | 0 / 222,156 |
| Average hands per table | 144.090 | 144.165 |
| Tables reaching the hand cap | 0 | 0 |

Batch `a` averaged 13.90 versus 13.70 (+0.20); batch `b` averaged 15.50 for both versions. A single changed score makes this sparse evidence. Neither the small positive sample difference nor the unchanged scores demonstrate strategy superiority or equivalence. This fixed field does not predict tournament results.

## Correctness and functional validation

- The upload bundle checker passed; the bundle contains `agent.py` and `preflop_policy.json` (97,962 bytes).
- 342 legal-action checks and 90 memory checks passed.
- The independent oracle passed 124 checks, with maximum absolute equity error 2e-14. Two previously incorrect call decisions now fold; their private states are omitted.
- The public oracle passed 150 checks, including 30 joint cases, with maximum absolute error 3.33e-15. All 21 side-pot regressions passed.
- A zero-bank normal-engine run used ten tables capped at 20 hands, 1 ms decisions and no time bank. It recorded 0 / 100 candidate failed decisions and 0 / 181 opponent failed decisions, with no process errors.

These equity checks establish correctness within the existing heuristic opponent-range model. They do not establish calibrated opponent probabilities or a GTO policy.

The required 200-table three-player reference match used seed `exact-river-v6-reference` against `check_or_fold` and `min_raiser`. V6 averaged **43.35 points**, with **154 firsts, five seconds and 41 thirds**, and zero failed decisions. The reference opponents averaged 29.50 and 27.15 points respectively, also with zero failures. All three places pay in this match, so this is a functional check rather than a competitive field estimate.

## Runtime observations

Direct `act` measurements exclude host and wire overhead.

| Measurement | Calls | p99 | Maximum | Calls over 1 ms |
| --- | ---: | ---: | ---: | ---: |
| Normal legal-state sample | 3,420 | 0.677 ms | 0.752 ms | 0 |
| Exact-river branch: 42 unknown cards, two opponents, two range contexts each | 960 | 0.479 ms | 0.520 ms | 0 |
| Isolated unchanged selection branch: eight players, seven contender groups | 480 | 0.426 ms | **2.042 ms** | **1** |
| Interleaved selection, sidepot v5 | 480 | 0.420 ms | 0.430 ms | 0 |
| Interleaved selection, exact-river v6 | 480 | 0.428 ms | 0.440 ms | 0 |

The exact-river measurement includes joint integration, range construction and pot pricing over 24 states. The interleaved comparison alternated both versions over the same 12 normal-engine selection states for 40 repeats. Both versions were loaded in one process, which increased the model-data heap. The isolated 2.042 ms selection outlier did not recur there; its cause is not established, including whether garbage collection contributed. **These results do not guarantee a strict 1 ms maximum.** Zero observed failures in the matches does not imply a zero future failure rate.

## Publication scope

This report contains sanitized aggregate results, public settings, seeds and hashes. Private card states, histories, raw per-table results, account identifiers, credentials and filesystem paths are excluded.
