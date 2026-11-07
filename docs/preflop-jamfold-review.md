# Preflop jam/fold research review

Reviewed snapshot: [`yifan/preflop-jamfold` at `54edbc7`](https://github.com/denfujita/poker/tree/54edbc770c1056882419597f879d515b3056795c). Its preflop code and exports are unchanged from `8b3aead`; the later commit adds separate postflop likelihood research.

The branch's root `agent.py` is byte-identical to v2 and does not load the preflop tables. Main retains validated v3, SHA-256 `2a831f886d03232967bc826ee25a6ad013797c9810308e970ace229601f650cd`. There is no integrated preflop-table candidate at the branch root to deploy or compare directly.

## Model limits

[`jamfold.py`](https://github.com/denfujita/poker/blob/54edbc770c1056882419597f879d515b3056795c/research/analysis/jamfold.py) solves a restricted chip-EV game:

- Everyone folds to the shover, who can jam or fold. There are no limps or small raises.
- Stacks are equal, with 0.5/1 blinds and no ante. Exported depths span 3–20 big blinds.
- The first caller ends the action. Overcalls and multiway all-ins are omitted; callers' hands are otherwise independent outside pairwise equity calculations.
- Flop selection keeps the strongest current made pair, which can differ from the pair with highest future equity.
- Payouts and ICM are absent. Its best-response diagnostic applies to this restricted game, not the full tournament.

Existing raises, unequal stacks, additional callers, deeper stacks, and payout pressure therefore need explicit handling before using the tables.

## Export gap

The runtime export contains three-card strength percentiles and aggregate jam/call shares. The solver's full `jam_by_bucket` and `call_by_bucket` policies are not included in `preflop.json`; the derived equity matrix, bucket CSV, and complete policy JSON also need regeneration.

An aggregate 40% jam share does not imply “jam the best 40% by heads-up equity.” That replaces the actual bucket policy with a monotone cutoff and may discard mixed or non-monotone choices. Such a cutoff should be labeled and tested as a new heuristic.

## Recommendation

Keep v3 while preparing a separate candidate that preserves its exposed-card conditioning, action-aware postflop behavior, and discard correction. Export a faithful bucket policy or explicitly define the replacement heuristic, specify unsupported-state fallbacks, then run legality/runtime checks and paired benchmarks against v3 using matched seeds, seating, and opponent fields.

The added postflop likelihood data are exploratory showdown-only observations, with missing uncontested bluffs and a rank-percentile prior that is not generally uniform. They are not yet a calibrated action-likelihood model or a validated bot improvement. This review does not integrate those data or tournament result files.
