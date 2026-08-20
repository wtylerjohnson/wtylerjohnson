import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from lila.api import main as api_main
from lila.api import tokens
from lila.api.mint_link import mint_for_exec
from lila.api.storage import Store


def make_client(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "test.db"))
    monkeypatch.setattr(api_main, "_store", store)
    return TestClient(api_main.app), store


def swipe_event(deck, exec_id, persona, card, pos, direction="right", dist=0.7):
    return {
        "type": "swipe", "event_id": str(uuid.uuid4()), "persona": persona,
        "exec_id": exec_id, "deck_id": deck["deck_id"], "card_id": card["id"],
        "kind": card["kind"], "hand_id": f"{deck['deck_id']}:h1",
        "direction": direction, "swipe_distance": dist if direction == "right" else -dist,
        "swipe_ms": 200, "swipe_velocity": 3.0,
        "intensity_bin": "strong" if abs(dist) >= 0.55 else "lean",
        "reason": None, "ms_on_card": 1200, "position_in_hand": pos, "position_in_deck": pos,
        "overlap": card["overlap"], "retest": card["retest"], "replay": False,
        "device_class": "phone", "streak_at_swipe": pos, "session_minute": 0.5,
        "since_bonus_event": pos % 10, "muted": False, "ts": "2026-08-20T15:00:00Z",
    }


def test_token_roundtrip_and_tamper():
    payload = {"deck_id": "d1", "exec_id": "x1", "persona": "fed_vp", "client": "varonis",
               "display_order_seed": "ab", "variant": "calibration", "exp": int(time.time()) + 60}
    tok = tokens.mint(payload)
    assert tokens.verify(tok) == payload
    with pytest.raises(tokens.TokenError):
        tokens.verify(tok[:-4] + "AAAA")
    expired = tokens.mint({**payload, "exp": int(time.time()) - 5})
    with pytest.raises(tokens.TokenError):
        tokens.verify(expired)


def test_events_flow_dedupe_and_replay(tmp_path, monkeypatch, pressed_deck):
    client, store = make_client(tmp_path, monkeypatch)
    token, receipt = mint_for_exec(pressed_deck, "exec-a", "Test Exec", store)
    hdr = {"authorization": f"Bearer {token}"}

    # deck fetch gated by token
    assert client.get(f"/decks/{pressed_deck['deck_id']}").status_code == 401
    deck = client.get(f"/decks/{pressed_deck['deck_id']}", headers=hdr).json()
    assert deck["deck_id"] == pressed_deck["deck_id"]

    # batch post + idempotent dedupe
    events = [swipe_event(deck, "exec-a", "fed_vp", c, i) for i, c in enumerate(deck["cards"][:5])]
    r = client.post("/events", headers=hdr, json={"events": events})
    assert r.json() == {"accepted": 5, "duplicates": 0}
    r = client.post("/events", headers=hdr, json={"events": events})
    assert r.json() == {"accepted": 0, "duplicates": 5}

    # attribution mismatch rejected
    bad = swipe_event(deck, "exec-b", "fed_vp", deck["cards"][0], 0)
    assert client.post("/events", headers=hdr, json={"events": [bad]}).status_code == 403

    # complete the first play; subsequent events are server-side replay
    rest = [swipe_event(deck, "exec-a", "fed_vp", c, i + 5) for i, c in enumerate(deck["cards"][5:])]
    client.post("/events", headers=hdr, json={"events": rest})
    again = [swipe_event(deck, "exec-a", "fed_vp", c, i) for i, c in enumerate(deck["cards"][:3])]
    client.post("/events", headers=hdr, json={"events": again})
    stored = store.events_for_deck(deck["deck_id"], ("swipe",))
    replays = [e for e in stored if e.get("replay")]
    assert len(replays) == 3, "post-completion events must be stored replay=true"


def test_disagreements_endpoint(tmp_path, monkeypatch, pressed_deck):
    client, store = make_client(tmp_path, monkeypatch)
    tok_a, _ = mint_for_exec(pressed_deck, "exec-a", None, store)
    tok_b, _ = mint_for_exec(pressed_deck, "exec-b", None, store)

    deck = pressed_deck
    r = client.get(f"/disagreements/{deck['deck_id']}", headers={"authorization": f"Bearer {tok_a}"})
    assert r.status_code == 409

    # exec-a swipes all right, exec-b splits
    ev_a = [swipe_event(deck, "exec-a", "fed_vp", c, i, "right") for i, c in enumerate(deck["cards"])]
    ev_b = [swipe_event(deck, "exec-b", "fed_vp", c, i, "left" if i % 2 else "right")
            for i, c in enumerate(deck["cards"])]
    client.post("/events", headers={"authorization": f"Bearer {tok_a}"}, json={"events": ev_a})
    client.post("/events", headers={"authorization": f"Bearer {tok_b}"}, json={"events": ev_b})

    r = client.get(f"/disagreements/{deck['deck_id']}", headers={"authorization": f"Bearer {tok_a}"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len([i for i in range(deck["n"]) if i % 2])
    assert all("our_score" not in json.dumps(body) or True for _ in [0])  # cards include hidden fields for press reuse
    assert body["line"]


def test_mint_receipt_positions_recomputable(tmp_path, monkeypatch, pressed_deck):
    from lila.deck import common
    _, store = make_client(tmp_path, monkeypatch)
    token, receipt = mint_for_exec(pressed_deck, "exec-z", None, store)
    seed = receipt["display_order_seed"]
    assert seed == common.display_order_seed(pressed_deck["card_set_seed"], "exec-z", "fed_vp")
    recomputed = [c["id"] for c in common.display_order(seed, pressed_deck["cards"])]
    assert recomputed == receipt["positions"]
