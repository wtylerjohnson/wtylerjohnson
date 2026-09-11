"""The monitor. Runs after every session and nightly. Writes a one-page
receipt and BLOCKS promotion of a new model if any check fails, saying which.
Also flags cards where the model and the crowd disagree hard; those return in
the next press inside the overlap-retest budget and as disagreement duels.
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
from lila.model.features import FEATURE_ALLOWLIST, FORBIDDEN_FEATURES
from lila.model.train import load_training_frame, train_lambdamart


def check_label_volume(labels_map: dict) -> dict:
    per_persona: dict[str, int] = {}
    for (_, persona, _, _) in labels_map:
        per_persona[persona] = per_persona.get(persona, 0) + 1
    pooled = len(labels_map)
    ok = pooled >= config.CLIENT_LABEL_GATE
    return {
        "check": "label_volume",
        "pooled_labels": pooled,
        "client_gate": config.CLIENT_LABEL_GATE,
        "per_persona": per_persona,
        "persona_gate": config.PERSONA_LABEL_GATE,
        "personas_past_gate": [p for p, n in per_persona.items() if n >= config.PERSONA_LABEL_GATE],
        "pass": ok,
        "detail": (f"{pooled} pooled labels meets the client gate" if ok else
                   f"insufficient labels: {pooled} pooled, gate is {config.CLIENT_LABEL_GATE}. "
                   "The ranker is not allowed to change the client artifact."),
    }


def check_sessions(sessions: dict) -> dict:
    quarantined = {k: v for k, v in sessions.items() if v["quarantine"]}
    rapid = {k: v["rapid_fire_runs"] for k, v in sessions.items() if v["rapid_fire_runs"]}
    return {
        "check": "session_quality",
        "sessions": len(sessions),
        "quarantined": list(quarantined.keys()),
        "rapid_fire_flagged": rapid,
        "pass": True,  # quarantine excludes labels; it does not block promotion by itself
        "detail": f"{len(quarantined)} session(s) quarantined (events retained, excluded from training pending review)",
    }


def check_inter_persona(labels_map: dict) -> dict:
    per_card: dict[str, dict[str, list[int]]] = {}
    for (_, persona, _, cid), lab in labels_map.items():
        per_card.setdefault(cid, {}).setdefault(persona, []).append(lab)
    agreements, comparisons = 0, 0
    for cid, by_p in per_card.items():
        personas = sorted(by_p)
        for i in range(len(personas)):
            for j in range(i + 1, len(personas)):
                a = sum(by_p[personas[i]]) / len(by_p[personas[i]])
                b = sum(by_p[personas[j]]) / len(by_p[personas[j]])
                comparisons += 1
                if (a >= 2) == (b >= 2):
                    agreements += 1
    rate = round(agreements / comparisons, 4) if comparisons else None
    return {"check": "inter_persona_agreement", "comparisons": comparisons,
            "agreement_rate": rate, "pass": True,
            "detail": "informational; trended across sessions in the history file"}


def check_importance_drift(booster, history_path: Path) -> dict:
    if booster is None:
        return {"check": "importance_drift", "pass": True, "detail": "no model trained; nothing to drift"}
    imp = booster.feature_importance(importance_type="gain")
    total = float(imp.sum()) or 1.0
    current = {f: round(float(v) / total, 4) for f, v in zip(FEATURE_ALLOWLIST, imp)}
    history = json.loads(history_path.read_text()) if history_path.exists() else []
    drift = None
    ok = True
    if history:
        prev = history[-1]["importances"]
        drift = round(sum(abs(current.get(f, 0) - prev.get(f, 0)) for f in FEATURE_ALLOWLIST) / 2, 4)
        ok = drift <= 0.5
    history.append({"importances": current})
    history_path.write_text(json.dumps(history[-20:], indent=2) + "\n")
    return {"check": "importance_drift", "l1_drift": drift, "pass": ok,
            "detail": "total variation distance between consecutive trainings; threshold 0.5"}


def check_salt_not_feature(booster) -> dict:
    names = list(booster.feature_name()) if booster else FEATURE_ALLOWLIST
    bad = [f for f in names if any(x in f for x in FORBIDDEN_FEATURES)]
    return {"check": "salt_not_feature", "pass": not bad,
            "detail": "salt, overlap, retest are held-out checks, never features" if not bad
            else f"FORBIDDEN feature present: {bad}"}


def check_calibration(decks: dict, labels_map: dict, pairs: list) -> dict:
    """Held-out fold: train on ~80 percent of groups, measure direction
    accuracy on the rest."""
    groups = sorted({(k[0], k[2]) for k in labels_map})
    if len(groups) < 3:
        return {"check": "calibration", "pass": True,
                "detail": f"only {len(groups)} session group(s); held-out fold not meaningful yet"}
    held = set(groups[:: max(1, len(groups) // 5)][:max(1, len(groups) // 5)])
    train_labels = {k: v for k, v in labels_map.items() if (k[0], k[2]) not in held}
    test_labels = {k: v for k, v in labels_map.items() if (k[0], k[2]) in held}
    booster, info = train_lambdamart(decks, train_labels, pairs, scope="calibration")
    if not booster or not test_labels:
        return {"check": "calibration", "pass": True, "detail": "insufficient rows for a held-out fold"}
    from lila.model.features import FeatureBuilder
    fb = FeatureBuilder(decks)
    ec, cc = fb.right_centroids(train_labels)
    correct = total = 0
    for (exec_id, persona, deck_id, cid), lab in test_labels.items():
        card = fb.cards.get(cid)
        if not card:
            continue
        pred = float(booster.predict(np.array([fb.row(card, persona, ec.get(exec_id), cc)]))[0])
        total += 1
        if (pred > 0) == (lab >= 2):
            correct += 1
    acc = round(correct / total, 4) if total else None
    return {"check": "calibration", "held_out_direction_accuracy": acc,
            "pass": acc is None or acc >= 0.55,
            "detail": f"held-out sessions: {len(held)}"}


def check_top5_movement(decks: dict, booster, labels_map: dict) -> dict:
    cards = {c["id"]: c for d in decks.values() for c in d["cards"] if not c["salt"]}
    hand_top5 = [c["id"] for c in sorted(cards.values(), key=lambda c: (-c["our_score"], c["id"]))[:5]]
    if booster is None:
        return {"check": "top5_movement", "pass": True, "hand_top5": hand_top5,
                "detail": "no model; artifact stays on hand score"}
    from lila.model.features import FeatureBuilder
    fb = FeatureBuilder(decks)
    ec, cc = fb.right_centroids(labels_map)
    persona = sorted({k[1] for k in labels_map})[0] if labels_map else ""
    scored = {cid: float(booster.predict(np.array([fb.row(c, persona, None, cc)]))[0])
              for cid, c in cards.items()}
    model_top5 = sorted(scored, key=lambda c: -scored[c])[:5]
    moved = [c for c in model_top5 if c not in hand_top5]
    return {"check": "top5_movement", "hand_top5": hand_top5, "model_top5": model_top5,
            "would_move": moved, "pass": True,
            "detail": "informational: rows the candidate model would move into the top five readout"}


def check_casino_bias(swipes: list[dict]) -> dict:
    """Right-swipe rate as a function of streak height, bonus proximity, and
    session minute. If mechanics push direction, flag the mechanic."""
    def right_rate(evs):
        return sum(1 for e in evs if e["direction"] == "right") / len(evs) if evs else None

    low_streak = [e for e in swipes if e.get("streak_at_swipe", 0) < 5]
    high_streak = [e for e in swipes if e.get("streak_at_swipe", 0) >= 10]
    near_bonus = [e for e in swipes if e.get("since_bonus_event", 99) <= 2]
    far_bonus = [e for e in swipes if e.get("since_bonus_event", 99) > 2]

    findings = []
    for name, a, b in [("streak", low_streak, high_streak), ("bonus_proximity", near_bonus, far_bonus)]:
        ra, rb = right_rate(a), right_rate(b)
        if ra is not None and rb is not None and len(a) >= 20 and len(b) >= 20 and abs(ra - rb) > 0.25:
            findings.append({"mechanic": name, "rates": [round(ra, 3), round(rb, 3)],
                             "action": "labels in the affected band down-weighted; mechanic named, exec not blamed"})
    return {"check": "casino_bias", "findings": findings, "pass": not findings,
            "detail": "right-swipe rate drift beyond 0.25 between game-state bands flags the mechanic"}


def hard_disagreements(decks: dict, booster, labels_map: dict) -> list[str]:
    if booster is None or not labels_map:
        return []
    from lila.model.features import FeatureBuilder
    fb = FeatureBuilder(decks)
    ec, cc = fb.right_centroids(labels_map)
    diffs = []
    preds = {}
    for (exec_id, persona, deck_id, cid), lab in labels_map.items():
        card = fb.cards.get(cid)
        if not card:
            continue
        if cid not in preds:
            preds[cid] = float(booster.predict(np.array([fb.row(card, persona, None, cc)]))[0])
    if not preds:
        return []
    vals = sorted(preds.values())
    med = vals[len(vals) // 2]
    for (exec_id, persona, deck_id, cid), lab in labels_map.items():
        if cid in preds:
            model_says_right = preds[cid] > med
            crowd_says_right = lab >= 2
            if model_says_right != crowd_says_right:
                diffs.append((abs(preds[cid] - med) * abs(lab - 1.5), cid))
    ranked = [cid for _, cid in sorted(set(diffs), reverse=True)]
    seen, out = set(), []
    for cid in ranked:
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out[:10]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("client")
    ap.add_argument("--db", default=os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "model" / "out"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    decks, labels_map, pairs, sessions, _ = load_training_frame(args.client, args.db)
    s = Store(args.db)
    swipes = [e for e in s.events_for_client(args.client)
              if e["type"] == "swipe" and not e.get("replay")]

    booster, train_info = train_lambdamart(decks, labels_map, pairs, scope="monitor")

    checks = [
        check_label_volume(labels_map),
        check_sessions(sessions),
        check_inter_persona(labels_map),
        check_salt_not_feature(booster),
        check_importance_drift(booster, out_dir / f"importance_history_{args.client}.json"),
        check_calibration(decks, labels_map, pairs),
        check_top5_movement(decks, booster, labels_map),
        check_casino_bias(swipes),
    ]
    failing = [c for c in checks if not c["pass"]]
    promote = not failing

    retest = hard_disagreements(decks, booster, labels_map)
    retest_path = out_dir / f"retest_{args.client}.json"
    retest_path.write_text(json.dumps(retest, indent=2) + "\n")

    receipt = {
        "client": args.client,
        "promotion_allowed": promote,
        "blocked_by": [c["check"] for c in failing],
        "verdict": ("PROMOTION ALLOWED" if promote else
                    "PROMOTION BLOCKED: " + "; ".join(f"{c['check']}: {c['detail']}" for c in failing)),
        "checks": checks,
        "lambdamart": train_info,
        "retest_cards": retest,
        "retest_file": str(retest_path),
    }
    receipt_path = out_dir / f"monitor_{args.client}.receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: receipt[k] for k in ("client", "promotion_allowed", "blocked_by", "verdict")},
                     indent=2))
    print(f"receipt: {receipt_path}")
    sys.exit(0 if promote else 3)


if __name__ == "__main__":
    main()
