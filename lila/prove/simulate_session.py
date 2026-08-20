"""Simulate an executive session against the live API, exactly as the phone
would: display-ordered cards, hands, swipes with raw gestures, reason chips,
one super like per hand (immediate or retroactive), per-hand orderings, duels,
batch posts with idempotent event ids.

The simulated exec's judgment correlates with the hidden score plus noise and
reliably left-swipes near-misses, so the report and trainer see signal. The
simulator is server-side tooling; unlike the app it MAY read hidden fields.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import httpx

from lila.deck import common


def play(api: str, token: str, hands_to_play: int | None, rng: random.Random,
         duplicate_first_batch: bool = False, persona_slug: str | None = None,
         seat_index: int = 1) -> dict:
    payload = json.loads(__import__("base64").urlsafe_b64decode(
        token.split(".")[0] + "==").decode())
    exec_id = payload["exec_id"]
    if payload.get("personas"):
        slug = persona_slug or sorted(payload["personas"])[0]
        seat = payload["personas"][slug]
        deck_id, persona, do_seed = seat["deck_id"], slug, seat["display_order_seed"]
    else:
        deck_id, persona = payload["deck_id"], payload["persona"]
        do_seed = payload["display_order_seed"]
    headers = {"authorization": f"Bearer {token}"}

    deck = httpx.get(f"{api}/decks/{deck_id}", headers=headers).json()
    cards = common.display_order(do_seed, deck["cards"])
    hands = deck["hands"][:hands_to_play] if hands_to_play else deck["hands"]

    def base(t, hand_i):
        return {"type": t, "event_id": str(uuid.uuid4()), "persona": persona,
                "exec_id": exec_id, "deck_id": deck_id, "hand_id": f"{deck_id}:h{hand_i+1}",
                "seat_index": seat_index, "replay": False, "ts": "2026-08-20T16:00:00Z"}

    sent = {"swipe": 0, "ordering": 0, "super_like": 0, "duel": 0}
    pos = 0
    first_batch = None
    for hand_i, size in enumerate(hands):
        batch = []
        rights = []
        super_used = False
        for pih in range(size):
            card = cards[pos]
            score = card["our_score"] + rng.gauss(0, 0.12)
            if card["salt"]:
                score -= 0.35  # attentive exec smells the dead card
            right = score >= 0.42
            dist = min(1.4, max(0.15, abs(score - 0.42) * 3 + rng.random() * 0.3))
            ev = {**base("swipe", hand_i), "card_id": card["id"], "kind": card["kind"],
                  "direction": "right" if right else "left",
                  "swipe_distance": round(dist if right else -dist, 4),
                  "swipe_ms": rng.randint(120, 500), "swipe_velocity": round(dist * 4, 3),
                  "intensity_bin": "strong" if dist >= 0.55 else "lean",
                  "reason": rng.choice(["fit", "timing", None]) if right else rng.choice(["wrong category", "closed or dead", None]),
                  "ms_on_card": rng.randint(900, 4000),
                  "position_in_hand": pih, "position_in_deck": pos,
                  "overlap": card["overlap"], "retest": card["retest"],
                  "device_class": "phone", "streak_at_swipe": pih + 1,
                  "session_minute": round(pos * 0.08, 2),
                  "since_bonus_event": pos % 12, "muted": False}
            batch.append(ev)
            if right:
                rights.append(card)
                if not super_used and score > 0.75:
                    batch.append({**base("super_like", hand_i), "card_id": card["id"],
                                  "kind": card["kind"], "mode": "immediate"})
                    super_used = True
            pos += 1

        ranked = sorted(rights, key=lambda c: -(c["our_score"] + rng.gauss(0, 0.08)))[:8]
        if ranked:
            batch.append({**base("ordering", hand_i),
                          "ranked_card_ids": [c["id"] for c in ranked],
                          "kinds": [c["kind"] for c in ranked]})
            if not super_used:
                batch.append({**base("super_like", hand_i), "card_id": ranked[0]["id"],
                              "kind": ranked[0]["kind"], "mode": "retroactive"})
        for i in range(0, len(ranked) - 1, 2):
            a, b = ranked[i], ranked[i + 1]
            winner = a if a["our_score"] + rng.gauss(0, 0.1) >= b["our_score"] else b
            batch.append({**base("duel", hand_i), "card_a": a["id"], "card_b": b["id"],
                          "kinds": [a["kind"], b["kind"]], "winner": winner["id"],
                          "sampling_reason": "recent_rights", "response_ms": rng.randint(800, 4000)})

        r = httpx.post(f"{api}/events", headers=headers, json={"events": batch})
        r.raise_for_status()
        for ev in batch:
            sent[ev["type"]] += 1
        if first_batch is None:
            first_batch = batch
        if duplicate_first_batch and hand_i == 0:
            # airplane-mode recovery: the queue re-posts, the server dedupes
            r2 = httpx.post(f"{api}/events", headers=headers, json={"events": first_batch})
            assert r2.json()["duplicates"] == len(first_batch), "dedupe failed"
            sent["redelivered_deduped"] = len(first_batch)

    return {"persona": persona, "exec_id": exec_id, "deck_id": deck_id, "sent": sent}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--token", action="append", required=True)
    ap.add_argument("--hands", type=int, default=None)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--dupe-first-batch", action="store_true")
    ap.add_argument("--persona", default=None, help="which seat to sit; defaults to first persona on the token")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    results = [play(args.api, t, args.hands, rng, args.dupe_first_batch, args.persona) for t in args.token]
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
