"""The hosted event endpoint. One small FastAPI service; storage and deploy
target behind adapters; the PWA stays static on Netlify, only this needs a host.

POST /events           typed batch (swipe | ordering | super_like | duel)
GET  /decks/{deck_id}  pressed deck JSON, the only read the app makes in play
GET  /disagreements/{deck_id}  the cross-executive disagreement deck
GET  /healthz

Auth on everything but healthz: signed deck token, Authorization: Bearer or ?t=.
Replay detection is server-side as well as client-side: once a token's first
play is complete, later swipes store replay=true regardless of the client.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from lila import config
from lila.api import tokens
from lila.api.storage import Store

app = FastAPI(title="lila-swipe-api")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_store: Store | None = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store(os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    return _store


def auth(request: Request) -> dict:
    tok = None
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        tok = header[7:]
    tok = tok or request.query_params.get("t")
    if not tok:
        raise HTTPException(401, "missing token")
    try:
        payload = tokens.verify(tok)
    except tokens.TokenError as e:
        raise HTTPException(401, str(e))
    payload["_token_id"] = tok.split(".")[1][:32]
    rec = store().any_token_row(payload["_token_id"])
    if rec and rec["revoked"]:
        raise HTTPException(403, "token revoked")
    # persona -> deck binding: the exec's seat choice must match the deck.
    # New tokens carry a personas map. Legacy tokens (one persona, one deck_id)
    # still resolve to a one-seat table.
    if payload.get("personas"):
        payload["_deck_to_persona"] = {
            p["deck_id"]: slug for slug, p in payload["personas"].items()
        }
    elif payload.get("persona") and payload.get("deck_id"):
        payload["_deck_to_persona"] = {payload["deck_id"]: payload["persona"]}
    else:
        payload["_deck_to_persona"] = {}
    return payload


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/decks/{deck_id}")
def get_deck(deck_id: str, payload: dict = Depends(auth)):
    if deck_id not in payload["_deck_to_persona"]:
        raise HTTPException(403, "token does not carry this deck")
    deck = store().get_deck(deck_id)
    if not deck:
        raise HTTPException(404, "deck not loaded")
    return deck


@app.post("/events")
async def post_events(request: Request, payload: dict = Depends(auth)):
    body = await request.json()
    events = body.get("events", [])
    if not isinstance(events, list):
        raise HTTPException(400, "events must be a list")
    deck_to_persona = payload["_deck_to_persona"]
    for ev in events:
        if ev.get("type") not in config.EVENT_TYPES:
            raise HTTPException(400, f"unknown event type: {ev.get('type')}")
        if ev.get("deck_id") not in deck_to_persona:
            raise HTTPException(403, "event deck does not match token")
        if ev.get("exec_id") != payload["exec_id"]:
            raise HTTPException(403, "event attribution does not match token")
        if ev.get("persona") != deck_to_persona[ev.get("deck_id")]:
            raise HTTPException(403, "event persona does not match the seat that owns this deck")
        for req in ("event_id", "hand_id", "ts"):
            if not ev.get(req):
                raise HTTPException(400, f"event missing {req}")

    # Replay is per deck: a token carries several persona decks, each with its
    # own first-play completeness.
    s = store()
    result = {"accepted": 0, "duplicates": 0}
    for deck_id in {ev["deck_id"] for ev in events}:
        deck_events = [ev for ev in events if ev["deck_id"] == deck_id]
        rec = s.get_token(payload["_token_id"], deck_id)
        force_replay = bool(rec and rec["first_play_complete"])
        r = s.insert_events(deck_events, force_replay=force_replay)
        result["accepted"] += r["accepted"]
        result["duplicates"] += r["duplicates"]
        deck = s.get_deck(deck_id)
        if deck and rec and not rec["first_play_complete"]:
            if s.distinct_first_play_swipes(payload["exec_id"], deck_id) >= deck["n"]:
                s.mark_first_play_complete(payload["_token_id"], deck_id)
    return result


@app.get("/disagreements/{deck_id}")
def disagreements(deck_id: str, payload: dict = Depends(auth)):
    """Once a second executive finishes the same deck, issue the short
    disagreement deck: cards the two execs split on. Names optional; this
    payload carries none."""
    s = store()
    deck = s.get_deck(deck_id)
    if not deck:
        raise HTTPException(404, "deck not loaded")
    execs = s.execs_on_deck(deck_id)
    if len(execs) < 2:
        raise HTTPException(409, "fewer than two executives have played this deck")
    swipes = [e for e in s.events_for_deck(deck_id, ("swipe",)) if not e.get("replay")]
    n = deck["n"]
    finished = [x for x in execs if len({e["card_id"] for e in swipes if e["exec_id"] == x}) >= 0.8 * n]
    if len(finished) < 2:
        raise HTTPException(409, "fewer than two executives have finished this deck")
    a, b = finished[:2]
    directions: dict[str, dict[str, str]] = {}
    for e in swipes:
        if e["exec_id"] in (a, b):
            directions.setdefault(e["card_id"], {})[e["exec_id"]] = e["direction"]
    split_ids = [cid for cid, d in directions.items()
                 if len(d) == 2 and d[a] != d[b]]
    cards = [c for c in deck["cards"] if c["id"] in set(split_ids)]
    return {
        "deck_id": deck_id,
        "count": len(cards),
        "line": "Someone at your company saw these differently.",
        "cards": cards,
    }
