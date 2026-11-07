# Frozen HU exact-river candidate validation

The candidate averages **14.25 points**, versus **14.40** for v6, in 200 matched eight-player tables against seven frozen v6 bots. The paired change is **-0.150 points**, with approximate paired 95% t interval **[-0.959, +0.659]**; 10 table scores changed. The two seed batches disagree in direction. These results establish no tournament-point improvement.

| Check | Result |
|---|---|
| Package and manifest | Passed; exactly agent.py and preflop_policy.json |
| Legal action / malformed memory | 342 / 90 passed |
| Public oracle | 335 checks, zero failures |
| Independent oracle / causal replay | 961 comparisons; all 84 expected action changes matched |
| Zero-bank upload-like probe | 0 failures / 100 candidate decisions |
| Required 200 reference tables | 42.75 points; 148 first, 11 second, 41 third; zero failures |
| Exact HU branch, 960 calls | p99 0.287 ms, max 0.429 ms |
| Matched field failures | 0 / 28099 candidate decisions |

The opponents had five failed decisions across four paired tables; both candidate and control heroes had zero. All four affected paired hero-score deltas were zero. Excluding those pairs gives -0.153 points across 196 pairs; the primary result above retains all preselected tables.

The first normal timing run had one unchanged-turn call at 1.097 ms; its repeat stayed below 0.803 ms. Direct timings exclude host and wire delivery and do not guarantee a strict 1 ms maximum.

Exact weighted equity removes sampling variance within the existing opponent model. It does not validate that model or convert chip EV into tournament-point utility. New integration atop another base requires fresh checks.

- Candidate source: `38ed571635c946ccd65ece23893f37b6a27cd72fb82e1d8a36805ac06dc96112`
- Baseline source: `2fe4de9a0d6f35fc5c3bb0aaccf47699e81e0eef2346662ac825d2f67e0f19d5`
- Policy asset: `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`
- Checked ZIP: `6b856bbac82f852c6be3e0e293448a7a9c1b0388ab41df805af9f7e6d943c5c9`

Fixed batches: `hu-exact-v7-strong-a` and `hu-exact-v7-strong-b`, 100 matched tables each. Only aggregate results are included; private histories and raw table records are excluded.
