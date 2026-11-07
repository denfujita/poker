# Restricted preflop jam/fold adapter

This candidate preserves tight-v4 outside a narrow small-blind versus big-blind preflop subgame. It uses the existing 40-bucket, three-card policy asset's actual jam and call probabilities rather than replacing mixed buckets with a threshold. Ordinary tight-v4 opening frequencies remain unchanged.

## Supported domain

- Hero is the small blind with an unopened pot, or the big blind facing the small blind's sole all-in raise. Heads-up, the button is the small blind.
- All nonblinds already folded. No limps, calls, checks, additional raises, or antes occurred. Blind posts and current pot/call amounts must match.
- Blinds are exactly 0.5/1; both blinds began with the same stack at exactly 3, 5, 7, 10, 12, 15, or 20 big blinds. There is no nearest-depth interpolation.
- The table currently has 2, 3, 4, 6, or 8 non-busted seats. Folded nonblinds' stacks are irrelevant because they contributed no chips and cannot overcall.
- The full bucket vector exists and the chosen action is legal.

A fractional probability is sampled with a generator local to the decision, seeded from table ID, hand number, seat, action kind, depth, and canonical holding. Repeated requests return the same choice; other tables, memory, card order, and global RNG activity do not affect it. A chart fold is terminal and cannot reach later equity/raise logic.

## Model limits

This is an approximate restricted-action chip-EV policy, not GTO for the full variant. Its equity buckets use a particular flop-discard model; the solved action tree excludes limps and small raises, and it does not optimize tournament ICM. Exact domain matching does not establish a performance gain.

In a causal replay of 55,560 eligible preflop decisions from Practice 5, the adapter triggered zero times. There were 6,042 states with nonblinds already folded without contributing chips, only 19 with equal blind starting totals, and none at an exact supported depth. Filler hero tables were excluded. This measures observed v3 trajectories, not trajectories produced by the candidate; private histories remain unpublished.

## Verification

`tools/check_jamfold_integration.py` uses official protocol objects and the real `Agent.act` entry point. It checks all 40 buckets across both branches, seven depths, and five table sizes; legal actions; terminal zero/one-probability decisions; deterministic mixtures; and equality with frozen v4 outside the gate.

The initial run passed 15,255 assertions. A configured 35% mixture selected the action on 36.45% of 2,000 jam decisions and 34.8% of 2,000 call decisions. All 20 unsupported-state comparisons matched v4. An independent audit passed 10,995 assertions, including busted-seat gaps, reversed blind-post order, and 24,000 mixed-action trials. Simulator performance and runtime checks are separate promotion requirements.

Run with the official kit environment and the frozen baseline's policy file beside its source:

```sh
python tools/check_jamfold_integration.py agent.py --baseline /path/to/tight-v4/agent.py
```

Candidate source SHA-256: `118d248bd5629cd96a06b877a9e3d4deba0ee77bf9ca0c2129fa2564370bfba2`. Policy asset SHA-256: `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`. Main and the active tournament bot remain frozen tight v4 pending promotion review.
