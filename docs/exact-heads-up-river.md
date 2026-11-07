# Exact heads-up river candidate

Source SHA-256: `38ed571635c946ccd65ece23893f37b6a27cd72fb82e1d8a36805ac06dc96112`.
Required policy JSON SHA-256: `8f7f0a9c425aa496f6a1eabaa83fbc526ea01482152e11a52e2896006b1ade98`.

V6 still samples 24 possible showdowns when exactly one live opponent remains on the river. With that opponent's exposed card fixed, only one card is unknown. Sampling can alter a call/fold decision near its EV threshold even though enumeration is inexpensive.

This candidate enumerates every legal hidden card when the board has five cards, the hero has two retained cards, and the sole live opponent has exactly one exposed card. It preserves the existing action-likelihood model, removes the same own/discarded/public cards from the deck, and divides weighted wins plus half of weighted ties by total weight. Eligible pot groups share that result; empty contender groups remain certain returns. Other game states and strategy thresholds are unchanged.

The result is exact within the existing heuristic range model. It does not calibrate that model, add opponent learning, or solve GTO play.

## Evidence and status

- `tools/check_heads_up_river.py` passes 335 assertions with a frozen v6 baseline, or 174 without it. Its 58 synthetic equity cases cover weights, ties, blockers, and group shape; the baseline run reproduces sampling error and checks 80 excluded-domain cases in ordinary and grouped modes.
- An independent audit passed 1,354 assertions and 941 replayed river states. Private cards and replay fixtures are not published.
- Remote safety, timing, normal-engine matches, and deployment remain pending. Main and the active upload are unchanged v6. No new strength claim is made.

Run with the official kit environment and keep each source's policy sidecar alongside it:

```sh
python tools/check_heads_up_river.py agent.py --baseline /path/to/frozen-v6/agent.py
```

The existing public benchmark reports apply to their named source hashes, not this candidate.
