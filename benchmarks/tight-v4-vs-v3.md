# Tight v4 paired benchmark

In 200 matched pairs of eight-player tables (200 tables per version), tight v4 averaged **23.5 points** against seven v3 opponents; the v3 control averaged **13.9 points** against the same field. The paired gain was **+9.6 points/table**, with a 95% Student-t interval of **+6.30 to +12.90**. Both fixed seed batches favored v4.

| Metric | v3 control | tight v4 |
|---|---:|---:|
| Mean points/table | 13.9 | 23.5 |
| Top-three finishes | 79/200 | 158/200 |
| Outright wins | 33/200 | 25/200 |
| Failed hero decisions | 0/19,092 | 0/33,255 |

The improvement came from paid finishes; win rate fell. These results describe a fixed v3 field and do not establish tournament-field performance.

Each version used the same table seeds and initial seats: `preflop-jamfold-strong-a` and `preflop-jamfold-strong-b`, 100 tables each. Their paired mean gains were +11.5 and +7.7 points. The simulator used the normal SDK guest protocol, 1 ms decisions, a 100 ms table bank, eight 2,000-chip stacks, a 250-hand cap, and 50/30/20 payouts. Points came from authoritative final engine results, including ICM if needed. There were no hand-cap stops or failed decisions in either field. Source and asset hashes, finish counts, and interval details are in the JSON aggregate.

V4 also passed the entire ZIP upload checker, 342 representative legality checks, 90 malformed-memory checks, a ten-table zero-bank probe, and the required 200-table reference match. Its measured act p99 was 0.716 ms and maximum 0.775 ms over 3,420 calls. Act timing excludes host/wire delivery; the normal-engine tests check the full guest path.
