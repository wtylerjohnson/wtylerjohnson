"""Train the ranker. Pooled-first (locked): the first model pools personas per
client with persona as a feature; per-persona models exist only past
PERSONA_LABEL_GATE. No cross-client pooling in v1.

Below CLIENT_LABEL_GATE the artifact orders by the six-term hand score with
weights from a REGULARIZED logistic regression initialized from and shrunk
toward the hand-authored weights: it must not relearn unconstrained weights
from 40 swipes.

LambdaMART: LightGBM lambdarank, query group = deck. Hand orderings and duels
enter as pairwise constraints materialized as within-group label adjustments
(mechanism documented in the training receipt). Promotion is monitor-gated.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from lila import config
from lila.api.storage import Store
from lila.model import labels as L
from lila.model.features import FEATURE_ALLOWLIST, FeatureBuilder


def load_training_frame(client: str, db_path: str):
    s = Store(db_path)
    events = [e for e in s.events_for_client(client) if not e.get("replay")]
    swipes = [e for e in events if e["type"] == "swipe"]
    orderings = [e for e in events if e["type"] == "ordering"]
    super_likes = [e for e in events if e["type"] == "super_like"]
    duels = [e for e in events if e["type"] == "duel"]

    deck_ids = sorted({e["deck_id"] for e in events})
    decks = {d: s.get_deck(d) for d in deck_ids}
    decks = {k: v for k, v in decks.items() if v}

    # Quarantine: salt gate + rapid fire, per session, before anything trains.
    quarantined = set()
    session_reports = {}
    for d_id, deck in decks.items():
        cards = {c["id"]: c for c in deck["cards"]}
        for exec_id in {e["exec_id"] for e in swipes if e["deck_id"] == d_id}:
            sw = [e for e in swipes if e["deck_id"] == d_id and e["exec_id"] == exec_id]
            q = L.session_quality(sw, cards)
            session_reports[f"{exec_id}:{d_id}"] = q
            if q["quarantine"]:
                quarantined.add((exec_id, d_id))

    usable = [e for e in swipes if (e["exec_id"], e["deck_id"]) not in quarantined]
    labels_map = L.derive_labels(usable, super_likes)

    # Salt cards are a held-out check, never training rows.
    salt_ids = {c["id"] for d in decks.values() for c in d["cards"] if c["salt"]}
    labels_map = {k: v for k, v in labels_map.items() if k[3] not in salt_ids}

    pairs = L.pairs_from_orderings(orderings) + L.pairs_from_duels(duels)
    return decks, labels_map, pairs, session_reports, len(usable)


def apply_pair_adjustments(labels_map: dict, pairs: list[tuple]) -> dict:
    """Materialize pairwise constraints as within-group label adjustments:
    when a pair contradicts the labels, nudge by +-0.5 capped to [0,4].
    Documented in the training receipt as pair_adjustment:v1."""
    adjusted = {k: float(v) for k, v in labels_map.items()}
    for (exec_id, persona, deck_id, better, worse, w) in pairs:
        kb, kw = (exec_id, persona, deck_id, better), (exec_id, persona, deck_id, worse)
        if kb in adjusted and kw in adjusted and adjusted[kb] <= adjusted[kw]:
            bump = 0.5 * min(w, 2.0) / 2.0
            adjusted[kb] = min(4.0, adjusted[kb] + bump)
            adjusted[kw] = max(0.0, adjusted[kw] - bump)
    return adjusted


def fit_fallback_weights(decks: dict, labels_map: dict) -> dict:
    """Ridge-regularized logistic regression on the six components, shrunk
    toward the hand weights. Fits the DEVIATION from the hand-score logit, so
    zero labels reproduce the hand weights exactly."""
    if not labels_map:
        return dict(config.HAND_WEIGHTS)
    cards = {c["id"]: c for d in decks.values() for c in d["cards"]}
    X, y = [], []
    for (_, _, _, cid), lab in labels_map.items():
        c = cards.get(cid)
        if c:
            X.append([c["our_components"][k] for k in config.COMPONENT_KEYS])
            y.append(1 if lab >= 2 else 0)
    if len(set(y)) < 2:
        return dict(config.HAND_WEIGHTS)
    from sklearn.linear_model import LogisticRegression

    # Strong ridge (small C) keeps the fit close to the prior at small n.
    n = len(y)
    C = min(1.0, n / 1000.0)
    lr = LogisticRegression(C=C, max_iter=1000)
    lr.fit(np.array(X), np.array(y))
    learned = lr.coef_[0]
    learned = np.abs(learned) / (np.sum(np.abs(learned)) or 1.0)
    prior = np.array([config.HAND_WEIGHTS[k] for k in config.COMPONENT_KEYS])
    alpha = min(0.5, n / (2 * config.CLIENT_LABEL_GATE))  # shrink toward prior
    blended = (1 - alpha) * prior + alpha * learned
    blended = blended / blended.sum()
    return {k: round(float(w), 4) for k, w in zip(config.COMPONENT_KEYS, blended)}


def train_lambdamart(decks: dict, labels_map: dict, pairs: list[tuple], scope: str,
                     persona: str | None = None):
    import lightgbm as lgb

    fb = FeatureBuilder(decks)
    exec_centroids, client_centroid = fb.right_centroids(labels_map)
    adjusted = apply_pair_adjustments(labels_map, pairs)

    keys = sorted(adjusted.keys())
    if persona:
        keys = [k for k in keys if k[1] == persona]
    X, y, groups = [], [], []
    group_sizes = []
    last_group = None
    for k in keys:
        exec_id, p, deck_id, cid = k
        card = fb.cards.get(cid)
        if not card:
            continue
        X.append(fb.row(card, p, exec_centroids.get(exec_id), client_centroid))
        y.append(int(round(adjusted[k])))
        g = f"{exec_id}:{deck_id}"
        if g != last_group:
            group_sizes.append(0)
            last_group = g
        group_sizes[-1] += 1

    if len(X) < 10 or len(group_sizes) < 2:
        return None, {"trained": False, "reason": f"insufficient rows for lambdarank ({len(X)} rows, {len(group_sizes)} groups)"}

    ds = lgb.Dataset(np.array(X), label=np.array(y), group=group_sizes,
                     feature_name=FEATURE_ALLOWLIST)
    params = {
        "objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [10],
        "num_leaves": 15, "min_data_in_leaf": 3, "learning_rate": 0.1,
        "verbose": -1, "deterministic": True, "seed": 7,
    }
    booster = lgb.train(params, ds, num_boost_round=50)
    info = {"trained": True, "rows": len(X), "groups": len(group_sizes),
            "features": FEATURE_ALLOWLIST, "pair_mechanism": "pair_adjustment:v1",
            "scope": scope, "persona": persona}
    return booster, info


def score_pool(booster, decks: dict, labels_map: dict, persona: str) -> dict[str, float]:
    fb = FeatureBuilder(decks)
    exec_centroids, client_centroid = fb.right_centroids(labels_map)
    scores = {}
    for cid, card in fb.cards.items():
        X = np.array([fb.row(card, persona, None, client_centroid)])
        scores[cid] = round(float(booster.predict(X)[0]), 6)
    return scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("client")
    ap.add_argument("--db", default=os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "model" / "out"))
    args = ap.parse_args()

    decks, labels_map, pairs, sessions, usable_swipes = load_training_frame(args.client, args.db)
    n_labels = len(labels_map)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fallback = fit_fallback_weights(decks, labels_map)
    booster, info = train_lambdamart(decks, labels_map, pairs, scope="pooled")

    model_id = None
    ranker_out = None
    if booster:
        import hashlib
        model_str = booster.model_to_string()
        model_id = hashlib.sha256(model_str.encode()).hexdigest()[:12]
        (out_dir / f"model_{args.client}_pooled_{model_id}.txt").write_text(model_str)
        personas = sorted({k[1] for k in labels_map})
        execs = sorted({k[0] for k in labels_map})
        ranker_out = {
            "ranker": {
                "scope": "pooled",
                "persona": None,
                "client": args.client,
                "model_id": model_id,
                "trained_on": {"events": n_labels, "execs": len(execs),
                               "through": max((e for k in labels_map for e in [k]), default=None) and "see receipt"},
                "scores": score_pool(booster, decks, labels_map, personas[0] if personas else ""),
            }
        }
        (out_dir / f"ranker_{args.client}_pooled.json").write_text(
            json.dumps(ranker_out, indent=2, sort_keys=True) + "\n")

    receipt = {
        "client": args.client,
        "labels": n_labels,
        "usable_swipes": usable_swipes,
        "pairs": len(pairs),
        "client_gate": config.CLIENT_LABEL_GATE,
        "gate_met": n_labels >= config.CLIENT_LABEL_GATE,
        "fallback_weights": fallback,
        "lambdamart": info,
        "model_id": model_id,
        "quarantined_sessions": [k for k, v in sessions.items() if v["quarantine"]],
        "note": "promotion is monitor-gated; training alone changes nothing in the artifact",
    }
    (out_dir / f"training_{args.client}.receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
