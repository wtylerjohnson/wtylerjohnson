"""swipe_report.py <client>: the read after every session.

Our score is the hypothesis; the swipes are the observation. Per deck: our
rank vs the crowd's, per persona and pooled, overall and BY KIND (rival awards
and forecasts carry different label semantics than open notices; do not read
cross-kind agreement literally).

Evaluation hierarchy (locked): 1. NDCG@10  2. top-10 overlap
3. pairwise accuracy  4. Kendall tau (secondary whole-list diagnostic).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lila.api.storage import Store
from lila.deck import common
from lila.model import labels as L


def crowd_rank(deck: dict, labels_map: dict, orderings: list[dict], swipes: list[dict],
               persona: str | None = None) -> dict[str, int]:
    """Swipe-derived rank within a deck: label desc, tie-break by hand-ordering
    position, then ms_on_card ascending."""
    order_pos: dict[str, float] = {}
    for o in orderings:
        if persona and o["persona"] != persona:
            continue
        for pos, cid in enumerate(o["ranked_card_ids"]):
            order_pos[cid] = min(order_pos.get(cid, 99), pos)
    ms: dict[str, float] = {}
    for s in swipes:
        if persona and s["persona"] != persona:
            continue
        ms[s["card_id"]] = min(ms.get(s["card_id"], 1e12), s.get("ms_on_card", 1e12))

    per_card: dict[str, list[int]] = {}
    for (_, p, _, cid), lab in labels_map.items():
        if persona and p != persona:
            continue
        per_card.setdefault(cid, []).append(lab)
    mean_label = {cid: sum(v) / len(v) for cid, v in per_card.items()}

    ranked = sorted(mean_label,
                    key=lambda c: (-mean_label[c], order_pos.get(c, 99), ms.get(c, 1e12), c))
    return {cid: i for i, cid in enumerate(ranked)}


def our_rank(deck: dict, card_ids: set[str]) -> dict[str, int]:
    ranked = sorted([c for c in deck["cards"] if c["id"] in card_ids],
                    key=lambda c: (-c["our_score"], c["id"]))
    return {c["id"]: i for i, c in enumerate(ranked)}


def hierarchy(deck: dict, labels_map: dict, orderings, duels, swipes, persona=None) -> dict:
    cr = crowd_rank(deck, labels_map, orderings, swipes, persona)
    if not cr:
        return {"cards_labeled": 0}
    ours = our_rank(deck, set(cr.keys()))
    ours_sorted = sorted(ours, key=ours.get)
    gains = {}
    for (_, p, _, cid), lab in labels_map.items():
        if persona and p != persona:
            continue
        gains[cid] = max(gains.get(cid, 0), lab)
    pairs = L.pairs_from_orderings([o for o in orderings if not persona or o["persona"] == persona])
    pairs += L.pairs_from_duels([d for d in duels if not persona or d["persona"] == persona])
    scores = {c["id"]: c["our_score"] for c in deck["cards"]}
    tau = L.kendall_tau(ours, cr)
    return {
        "cards_labeled": len(cr),
        "ndcg_at_10": round(L.ndcg_at_k(ours_sorted, gains, 10), 4),
        "top10_overlap": L.top_k_overlap(ours_sorted, sorted(cr, key=cr.get), 10),
        "pairwise_accuracy": (round(v, 4) if (v := L.pairwise_accuracy(pairs, scores)) is not None else None),
        "kendall_tau": round(tau, 4) if tau is not None else None,
    }


def report(client: str, db_path: str) -> dict:
    s = Store(db_path)
    events = s.events_for_client(client)
    first_play = [e for e in events if not e.get("replay")]
    swipes = [e for e in first_play if e["type"] == "swipe"]
    orderings = [e for e in first_play if e["type"] == "ordering"]
    super_likes = [e for e in first_play if e["type"] == "super_like"]
    duels = [e for e in first_play if e["type"] == "duel"]

    deck_ids = sorted({e["deck_id"] for e in first_play})
    decks = {d: s.get_deck(d) for d in deck_ids}
    decks = {k: v for k, v in decks.items() if v}

    # Session quality first: quarantined sessions drop out of the comparison.
    sessions: dict = {}
    quarantined: set = set()
    for d_id, deck in decks.items():
        cards = {c["id"]: c for c in deck["cards"]}
        for exec_id in {e["exec_id"] for e in swipes if e["deck_id"] == d_id}:
            sw = [e for e in swipes if e["deck_id"] == d_id and e["exec_id"] == exec_id]
            q = L.session_quality(sw, cards)
            sessions[f"{exec_id}:{d_id}"] = q
            if q["quarantine"]:
                quarantined.add((exec_id, d_id))

    usable_swipes = [e for e in swipes if (e["exec_id"], e["deck_id"]) not in quarantined]
    labels_map = L.derive_labels(usable_swipes, super_likes)

    per_deck: dict = {}
    for d_id, deck in decks.items():
        dl = {k: v for k, v in labels_map.items() if k[2] == d_id}
        d_orderings = [o for o in orderings if o["deck_id"] == d_id]
        d_duels = [x for x in duels if x["deck_id"] == d_id]
        d_swipes = [x for x in usable_swipes if x["deck_id"] == d_id]
        entry = {"pooled": hierarchy(deck, dl, d_orderings, d_duels, d_swipes)}
        for persona in sorted({k[1] for k in dl}):
            entry[persona] = hierarchy(deck, dl, d_orderings, d_duels, d_swipes, persona)
        by_kind = {}
        for kind in sorted({c["kind"] for c in deck["cards"]}):
            kind_ids = {c["id"] for c in deck["cards"] if c["kind"] == kind}
            kl = {k: v for k, v in dl.items() if k[3] in kind_ids}
            if kl:
                agree = sum(1 for (e, p, dd, cid), lab in kl.items()
                            for c in [next(c for c in deck["cards"] if c["id"] == cid)]
                            if (lab >= 2) == (c["our_score"] >= 0.5))
                by_kind[kind] = {"labels": len(kl), "direction_agreement": round(agree / len(kl), 4)}
        entry["by_kind"] = by_kind

        # Salt catch rate per persona (usable sessions only).
        cards = {c["id"]: c for c in deck["cards"]}
        salt_by_persona = {}
        for persona in sorted({e["persona"] for e in d_swipes}):
            ss = [e for e in d_swipes if e["persona"] == persona and cards.get(e["card_id"], {}).get("salt")]
            if ss:
                salt_by_persona[persona] = round(sum(1 for e in ss if e["direction"] == "left") / len(ss), 4)
        entry["salt_catch_by_persona"] = salt_by_persona

        # Widest label spread across personas.
        spread = {}
        for (_, persona, _, cid), lab in dl.items():
            spread.setdefault(cid, {})[persona] = lab
        disagreements = sorted(
            ((cid, max(v.values()) - min(v.values()), v) for cid, v in spread.items() if len(v) > 1),
            key=lambda x: -x[1])
        entry["persona_disagreements"] = [
            {"card_id": cid, "spread": sp, "labels": v} for cid, sp, v in disagreements[:5] if sp > 0]
        per_deck[d_id] = entry

    out = {
        "client": client,
        "decks": per_deck,
        "sessions": sessions,
        "event_counts": {
            "swipes": len(swipes), "orderings": len(orderings),
            "super_likes": len(super_likes), "duels": len(duels),
            "replays_excluded": len(events) - len(first_play),
            "quarantined_sessions": len(quarantined),
        },
    }
    out["receipt"] = {
        "decks_covered": list(per_deck.keys()),
        "deck_hashes": {d: common.content_id(decks[d]) for d in per_deck},
        "execs": sorted({e["exec_id"] for e in swipes}),
        "labels_used": len(labels_map),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("client")
    ap.add_argument("--db", default=os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    rep = report(args.client, args.db)
    text = json.dumps(rep, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
