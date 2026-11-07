"""Demo: rank-and-reweight ranges over each opponent's ONE hidden card, and how much
card-removal between opponents (blockers) changes the marginals and our equity.

Scenario is hand-picked to stress blockers (all opponents show a K on an ace-high river and
bet/call), so the numbers are an upper-ish illustration, not an average effect.

Run: OMP_NUM_THREADS=1 .venv/bin/python -I ../bench/blocker_demo.py
"""

import itertools

import eval7

C = eval7.Card
DECK = [C(r + s) for r in "23456789TJQKA" for s in "shdc"]

HERO = [C("Js"), C("Jd")]
BOARD = [C("Ah"), C("7c"), C("2d"), C("9s"), C("4h")]  # river, so no runout randomness
SHOWN = [C("Ks"), C("Kd"), C("Kc")]  # each opponent's exposed card
F_CONTINUE = 0.30  # they bet/call with the top 30% of their current range
EPS = 0.10  # floor: any card keeps >= 10% of its weight (bluffs / model error)
RAMP = 0.10  # soft threshold width in percentile units


def candidates():
    seen = set(HERO) | set(BOARD) | set(SHOWN)
    return [c for c in DECK if c not in seen]


def ramp(q, lo, width):
    """0 below lo-width/2, 1 above lo+width/2, linear in between."""
    x = (q - (lo - width / 2)) / width
    return min(1.0, max(0.0, x))


def update_on_continue(weights, strength, f):
    """Bet/call: keep the top f of the CURRENT weighted range (weighted mid-rank percentile)."""
    cards = sorted(weights, key=lambda c: strength[c])
    total = sum(weights.values())
    out, below, i = {}, 0.0, 0
    while i < len(cards):  # handle ties as one block
        j = i
        while j < len(cards) and strength[cards[j]] == strength[cards[i]]:
            j += 1
        block = sum(weights[c] for c in cards[i:j])
        q = (below + block / 2) / total
        lik = EPS + (1 - EPS) * ramp(q, 1 - f, RAMP)
        for c in cards[i:j]:
            out[c] = weights[c] * lik
        below += block
        i = j
    return out


def normalize(w):
    t = sum(w.values())
    return {c: v / t for c, v in w.items()}


def main(n_opp):
    cand = candidates()
    shown = SHOWN[:n_opp]
    strength = [{h: eval7.evaluate([e, h] + BOARD) for h in cand} for e in shown]
    # Independent per-opponent posteriors (uniform prior, one bet/call update).
    w = [update_on_continue({h: 1.0 for h in cand}, strength[i], F_CONTINUE) for i in range(n_opp)]
    indep = [normalize(wi) for wi in w]

    # Exact joint: P(h_1..h_n) ∝ prod w_i(h_i) * [all distinct]. Marginals by enumeration.
    joint_marg = [dict.fromkeys(cand, 0.0) for _ in range(n_opp)]
    z = 0.0
    hero_val = eval7.evaluate(HERO + BOARD)
    win_exact = 0.0
    for combo in itertools.product(cand, repeat=n_opp):
        if len(set(combo)) < n_opp:
            continue
        p = 1.0
        for i, h in enumerate(combo):
            p *= w[i][h]
        if p == 0:
            continue
        z += p
        for i, h in enumerate(combo):
            joint_marg[i][h] += p
        best = max(strength[i][h] for i, h in enumerate(combo))
        win_exact += p * (1.0 if hero_val > best else 0.5 if hero_val == best else 0.0)
    joint_marg = [{c: v / z for c, v in m.items()} for m in joint_marg]
    win_exact /= z

    # Mean-field correction (cheap, any n): P_i(h) ∝ w_i(h) * prod_{j!=i} (1 - P_j(h)), iterate.
    mf = [dict(m) for m in indep]
    for _ in range(5):
        new = []
        for i in range(n_opp):
            new.append(normalize({h: w[i][h] * _prod(1 - mf[j][h] for j in range(n_opp) if j != i) for h in cand}))
        mf = new

    # Equity vs the field as product of heads-up (independence) vs exact joint.
    def p_beat(i, marg):
        return sum(p * (1.0 if hero_val > strength[i][h] else 0.5 if hero_val == strength[i][h] else 0.0) for h, p in marg[i].items())

    win_indep = _prod(p_beat(i, indep) for i in range(n_opp))
    win_mf = _prod(p_beat(i, mf) for i in range(n_opp))

    aces = [c for c in cand if str(c)[0] == "A"]
    print(f"\n=== {n_opp} opponents showing {' '.join(map(str, shown))}; board {' '.join(map(str, BOARD))}; hero {' '.join(map(str, HERO))}")
    print(f"candidates per opponent: {len(cand)} (aces left: {' '.join(map(str, aces))})")
    print(f"P(opp1 holds an ace):  independent {sum(indep[0][a] for a in aces):.3f}   mean-field {sum(mf[0][a] for a in aces):.3f}   exact joint {sum(joint_marg[0][a] for a in aces):.3f}")
    print(f"P(hero JJ wins):       independent {win_indep:.3f}   mean-field {win_mf:.3f}   exact joint {win_exact:.3f}")
    top = sorted(indep[0].items(), key=lambda kv: -kv[1])[:8]
    print("opp1 top cards after bet:", ", ".join(f"{c}:{p:.3f}" for c, p in top))


def _prod(xs):
    out = 1.0
    for x in xs:
        out *= x
    return out


if __name__ == "__main__":
    for n in (1, 2, 3):
        main(n)
