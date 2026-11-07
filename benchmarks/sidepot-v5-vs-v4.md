# Side-pot v5 versus v4

Side-pot v5 averaged **14.60 points per table** versus **14.15** for v4 over **200 matched eight-player tables**: a paired difference of **+0.45**. Only **four table scores changed** (three +20 and one +30; 196 unchanged). This is limited evidence of a small positive difference in one fixed field, not a strong improvement claim or a prediction of tournament performance.

## Exact versions

| Artifact | SHA-256 |
| --- | --- |
| Side-pot v5 agent | `b208a8970bfc314471e07efe1279815704749e2c4c2270b707be9b39b698d7de` |
| v4 agent | `47f1af369299958021af7a76b05940b5cbfbf935e9c1ebae7e823dc3f4cb8a33` |
| Unchanged preflop policy | `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98` |

The submission bundle hash was `49b48937a5af212ce6108cd55489a282a505878b42c393c7f1c639f00c9facee`. Validation and benchmark results apply to these frozen sources.

## Paired benchmark

One evaluated bot faced **seven copies of v4**. The control placed v4 in the same evaluated seat. Initial seating and deal seeds were matched and verified; final points and stacks were checked against authoritative engine results.

| Metric | Side-pot v5 | v4 control |
| --- | ---: | ---: |
| Tables | 200 | 200 |
| Mean points | 14.60 | 14.15 |
| First-place / outright wins | 25 (12.5%) | 23 (11.5%) |
| Top-three finishes | 90 (45.0%) | 88 (44.0%) |
| Evaluated-bot failed decisions | 0 / 29,084 | 0 / 29,057 |
| All-bot failed decisions | 0 / 222,156 | 0 / 222,328 |
| Hand-cap stops | 0 | 0 |

No table reached the cap, so first-place finishes here were outright wins. The means use authoritative points rather than reconstructing rewards from ranks.

| Seed | Tables per version | Side-pot v5 mean | v4 mean | Paired difference | Changed scores |
| --- | ---: | ---: | ---: | ---: | ---: |
| `mixed-jam-v5-strong-a` | 100 | 13.70 | 13.50 | +0.20 | 1 |
| `mixed-jam-v5-strong-b` | 100 | 15.50 | 14.80 | +0.70 | 3 |

### Uncertainty

- Paired t 95% interval for the mean difference: **[+0.0014, +0.8986] points**.
- Independent stratified paired-bootstrap 95% interval: **[+0.10, +0.95] points**, resampling paired differences within each seed batch.
- Exact two-sided sign-flip test on the four nonzero paired differences: **p = 0.125**.

The t interval barely excludes zero. The bootstrap is conditional on only four observed changes, and the sign-flip result does not supply strong evidence against no difference. These unadjusted intervals do not account for repeated model selection. More independent evidence is needed before claiming stronger play.

### Finishing positions

| Place | Side-pot v5 | v4 control |
| --- | ---: | ---: |
| 1 | 25 | 23 |
| 2 | 37 | 38 |
| 3 | 28 | 27 |
| 4 | 19 | 21 |
| 5 | 24 | 24 |
| 6 | 20 | 20 |
| 7 | 20 | 20 |
| 8 | 27 | 27 |

### Settings

- Variant: `flop_discard_reveal`; eight players, 2,000 starting chips each.
- Blinds: 10/20, 20/40, 30/60, 50/100, 80/160, 125/250, 200/400, 300/600, 500/1000, 800/1600, 1200/2400, 2000/4000; no ante. Levels last 20 hands and the final level repeats.
- Hand cap: 250; payouts: 50/30/20 points. One ordinary continuation per table; no resampling or ICM luck correction.
- Decision allowance: 1 ms; table time bank: 100 ms; memory limit: 65,536 bytes. Test concurrency: two tables.

## Required reference match and validation

Seed `sidepot-v5-reference`, 200 three-player tables against `check_or_fold` and `min_raiser`:

| Bot | Mean points | First / second / third | Failed decisions |
| --- | ---: | --- | ---: |
| Side-pot v5 | 42.60 | 146 / 14 / 40 | 0 |
| check_or_fold | 28.85 | 0 / 177 / 23 | 0 |
| min_raiser | 28.55 | 54 / 9 / 137 | 0 |

The submission checker, **342 legality states**, **90 malformed-memory checks**, and **21 side-pot regression checks** passed. A ten-table, 20-hand heads-up probe with 1 ms decisions and **zero time bank** reported **0/100 failed decisions** for the candidate and **0/180** for the opponent.

Correct accounting and controlled regressions do not establish exact equity estimates for every side-pot situation.

## Runtime limits

Measurements cover **`act` only**, excluding serialization, IPC, host delivery, and queueing.

- Across 3,420 representative calls: p50 **0.194 ms**, p99 **0.671 ms**, maximum **0.748 ms**, with none over 1 ms.
- Two unequal-all-in **eight-player** selection stress passes: 960 calls total, maximum **0.447 ms**, none over 1 ms.
- Additional **ten-player** stress passes: p99 about **0.508–0.513 ms**, with **3 of 960 calls above 1 ms** and maxima of **2.835 ms** and **2.128 ms**. This is a real tail-latency limitation; do not claim every decision stays under 1 ms.

Full normal-engine matches reported zero failed decisions. Reference-bot outcomes and offline timing do not guarantee tournament results.

## Data boundary

This report contains only source hashes, public test seeds/settings, and sanitized aggregate statistics. Private histories, account metadata, filesystem paths, and raw per-table records are excluded.
