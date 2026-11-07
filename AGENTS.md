# Repository instructions

- Preserve the submitted `agent.py` behavior unless the user requests a strategy change. Keep bot dependencies to the official kit's allowed imports.
- Read the official kit's `AGENTS.md`, `README.md`, and `RULES.md` before implementing a change. The kit is provided separately through the tournament portal.
- In this variant, discard one of three cards and expose one retained card simultaneously after the flop and before flop betting. All-in players also choose. All choices lock before any exposure is published. Showdown reveals both retained cards automatically; the discard stays private.
- Use the actual SDK action types and legal-action bounds. Raise amounts are whole street totals. Calls can be smaller than `to_call` when a stack is short.
- Do not keep mutable game state in globals or `self`, learn across tables, use the network from the bot, or perform background work between decisions. Use explicit per-table memory if later strategies need it.
- Target well below the 1 ms decision allowance. Run the submission checker, focused strategy tests, no-bank probe, and normal simulator before an authorized upload. Inspect failed decisions and tail latency, not only mean latency.
- Treat Monte Carlo chip-EV and opponent heuristics as approximations; do not label them GTO. Use actual table payouts/configuration rather than assuming fixed defaults.
- Keep credentials, API/account metadata, private hand histories, raw per-table data, and local paths out of commits. Commit only code, test tools, and sanitized aggregate benchmark evidence.
