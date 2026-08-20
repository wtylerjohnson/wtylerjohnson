"""Label derivation and ranking metrics, shared by the report, the trainer,
and the monitor. The relevance mapping lives HERE, in training code, never in
the browser (locked decision 5): raw gestures come in, labels come out, and
the mapping can be revised without an app release.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lila import config


# --------------------------------------------------------------------------
# Labels: 0 left-strong, 1 left-lean, 2 right-lean, 3 right-strong, 4 super like.
# Intensity is normalized per executive (within their session swipes), so one
# exec's flick and another's drag mean the same thing.
# --------------------------------------------------------------------------

def _zscores(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    sd = math.sqrt(var)
    if sd < 1e-9:
        return [0.0] * n
    return [(v - mean) / sd for v in values]


def derive_labels(swipes: list[dict], super_likes: list[dict]) -> dict[tuple, int]:
    """Returns {(exec_id, persona, deck_id, card_id): label 0..4}.
    Quarantined or replay events must be filtered by the caller."""
    by_exec: dict[str, list[dict]] = {}
    for s in swipes:
        by_exec.setdefault(s["exec_id"], []).append(s)

    labels: dict[tuple, int] = {}
    for exec_id, evs in by_exec.items():
        zs = _zscores([abs(e.get("swipe_distance", 0.0)) for e in evs])
        for e, z in zip(evs, zs):
            strong = z >= 0
            if e["direction"] == "right":
                label = 3 if strong else 2
            else:
                label = 0 if strong else 1
            labels[(exec_id, e["persona"], e["deck_id"], e["card_id"])] = label

    for sl in super_likes:
        labels[(sl["exec_id"], sl["persona"], sl["deck_id"], sl["card_id"])] = 4
    return labels


def pairs_from_orderings(orderings: list[dict]) -> list[tuple]:
    """(exec_id, persona, deck_id, better_card, worse_card, weight). Position
    gap weighting: adjacent 1.0, further apart heavier."""
    pairs = []
    for o in orderings:
        ids = o["ranked_card_ids"]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                w = 1.0 + (j - i - 1) * 0.25
                pairs.append((o["exec_id"], o["persona"], o["deck_id"], ids[i], ids[j], w))
    return pairs


def pairs_from_duels(duels: list[dict]) -> list[tuple]:
    """Duels are direct preferences and get full weight (locked: full weight,
    heavier than implied ordering pairs)."""
    pairs = []
    for d in duels:
        loser = d["card_b"] if d["winner"] == d["card_a"] else d["card_a"]
        pairs.append((d["exec_id"], d["persona"], d["deck_id"], d["winner"], loser, 2.0))
    return pairs


# --------------------------------------------------------------------------
# Metrics: the locked hierarchy is NDCG@10, top-10 overlap, pairwise accuracy,
# Kendall tau as a secondary whole-list diagnostic.
# --------------------------------------------------------------------------

def ndcg_at_k(ranked_ids: list[str], gains: dict[str, float], k: int = 10) -> float:
    def dcg(ids):
        return sum(gains.get(i, 0.0) / math.log2(pos + 2) for pos, i in enumerate(ids[:k]))
    ideal = sorted(gains, key=lambda i: -gains[i])
    idcg = dcg(ideal)
    return dcg(ranked_ids) / idcg if idcg > 0 else 0.0


def top_k_overlap(a_ids: list[str], b_ids: list[str], k: int = 10) -> int:
    return len(set(a_ids[:k]) & set(b_ids[:k]))


def pairwise_accuracy(pairs: list[tuple], scores: dict[str, float]) -> float | None:
    total, correct = 0.0, 0.0
    for (_, _, _, better, worse, w) in pairs:
        if better in scores and worse in scores:
            total += w
            if scores[better] > scores[worse]:
                correct += w
    return correct / total if total else None


def kendall_tau(rank_a: dict[str, int], rank_b: dict[str, int]) -> float | None:
    common_ids = [i for i in rank_a if i in rank_b]
    n = len(common_ids)
    if n < 2:
        return None
    conc = disc = 0
    for x in range(n):
        for y in range(x + 1, n):
            a = rank_a[common_ids[x]] - rank_a[common_ids[y]]
            b = rank_b[common_ids[x]] - rank_b[common_ids[y]]
            prod = a * b
            if prod > 0:
                conc += 1
            elif prod < 0:
                disc += 1
    denom = n * (n - 1) / 2
    return (conc - disc) / denom if denom else None


# --------------------------------------------------------------------------
# Session quality: the sample-aware salt gate and the rapid-fire signal.
# --------------------------------------------------------------------------

def binomial_p_at_most(k: int, n: int, p: float) -> float:
    """One-sided: P(X <= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def salt_gate(salt_swipes: list[dict]) -> dict:
    """No quarantine below SALT_MIN_JUDGMENTS. Then a one-sided binomial test
    against SALT_CATCH_NULL: quarantine only when the catch count is
    significantly below the null. Quarantine retains events, excludes from
    training pending review."""
    n = len(salt_swipes)
    caught = sum(1 for s in salt_swipes if s["direction"] == "left")
    if n < config.SALT_MIN_JUDGMENTS:
        return {"n": n, "caught": caught, "catch_rate": caught / n if n else None,
                "quarantine": False, "reason": f"below minimum {config.SALT_MIN_JUDGMENTS} salt judgments; gate not applied"}
    p_value = binomial_p_at_most(caught, n, config.SALT_CATCH_NULL)
    quarantine = p_value < config.SALT_ALPHA
    return {"n": n, "caught": caught, "catch_rate": caught / n, "p_value": round(p_value, 5),
            "quarantine": quarantine,
            "reason": ("catch rate significantly below null; session flagged lazy or confused"
                       if quarantine else "consistent with attentive play")}


def rapid_fire_runs(swipes: list[dict]) -> list[dict]:
    """Runs of RAPID_FIRE_RUN or more swipes under RAPID_FIRE_MS each."""
    ordered = sorted(swipes, key=lambda s: s.get("position_in_deck", 0))
    runs, current = [], []
    for s in ordered:
        if s.get("ms_on_card", 1e9) < config.RAPID_FIRE_MS:
            current.append(s)
        else:
            if len(current) >= config.RAPID_FIRE_RUN:
                runs.append(current)
            current = []
    if len(current) >= config.RAPID_FIRE_RUN:
        runs.append(current)
    return [{"start_position": r[0].get("position_in_deck"), "length": len(r)} for r in runs]


def session_quality(swipes_for_session: list[dict], deck_cards: dict[str, dict]) -> dict:
    salt_swipes = [s for s in swipes_for_session
                   if deck_cards.get(s["card_id"], {}).get("salt")]
    gate = salt_gate(salt_swipes)
    runs = rapid_fire_runs(swipes_for_session)
    return {**gate, "rapid_fire_runs": runs,
            "quarantine": gate["quarantine"],
            "flags": (["rapid_fire"] if runs else []) + (["salt_gate"] if gate["quarantine"] else [])}
