"""Storage adapter. SQLite default; the interface is the contract so a
Postgres implementation can slot in without touching handlers. No hard-coded
host anywhere; the DB path comes from the environment."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS decks (
  deck_id TEXT PRIMARY KEY,
  client TEXT NOT NULL,
  persona TEXT NOT NULL,
  deck_json TEXT NOT NULL,
  receipt_json TEXT,
  loaded_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tokens (
  token_id TEXT NOT NULL,
  exec_id TEXT NOT NULL,
  exec_name TEXT,
  deck_id TEXT NOT NULL,
  client TEXT NOT NULL,
  persona TEXT NOT NULL,
  variant TEXT NOT NULL,
  display_order_seed TEXT NOT NULL,
  positions_json TEXT NOT NULL,
  created_at REAL NOT NULL,
  first_play_complete INTEGER NOT NULL DEFAULT 0,
  revoked INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (token_id, deck_id)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  persona TEXT NOT NULL,
  exec_id TEXT NOT NULL,
  deck_id TEXT NOT NULL,
  hand_id TEXT NOT NULL,
  card_id TEXT,
  kind TEXT,
  replay INTEGER NOT NULL DEFAULT 0,
  ts TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  received_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_deck ON events (deck_id, exec_id, type);
CREATE INDEX IF NOT EXISTS idx_events_persona ON events (persona, type);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # decks -----------------------------------------------------------------
    def put_deck(self, deck: dict, receipt: dict | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO decks (deck_id, client, persona, deck_json, receipt_json, loaded_at)"
            " VALUES (?,?,?,?,?,?)",
            (deck["deck_id"], deck["client"], deck["persona"], json.dumps(deck),
             json.dumps(receipt) if receipt else None, time.time()),
        )
        self.conn.commit()

    def get_deck(self, deck_id: str) -> dict | None:
        row = self.conn.execute("SELECT deck_json FROM decks WHERE deck_id=?", (deck_id,)).fetchone()
        return json.loads(row["deck_json"]) if row else None

    # tokens ----------------------------------------------------------------
    def put_token(self, rec: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO tokens (token_id, exec_id, exec_name, deck_id, client, persona,"
            " variant, display_order_seed, positions_json, created_at, first_play_complete, revoked)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,0,0)",
            (rec["token_id"], rec["exec_id"], rec.get("exec_name"), rec["deck_id"], rec["client"],
             rec["persona"], rec["variant"], rec["display_order_seed"],
             json.dumps(rec["positions"]), time.time()),
        )
        self.conn.commit()

    def get_token(self, token_id: str, deck_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM tokens WHERE token_id=? AND deck_id=?", (token_id, deck_id)
        ).fetchone()

    def any_token_row(self, token_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM tokens WHERE token_id=?", (token_id,)).fetchone()

    def exec_history_count(self, exec_id: str, client: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT token_id) c FROM tokens WHERE exec_id=? AND client=?",
            (exec_id, client),
        ).fetchone()
        return row["c"]

    def mark_first_play_complete(self, token_id: str, deck_id: str) -> None:
        self.conn.execute(
            "UPDATE tokens SET first_play_complete=1 WHERE token_id=? AND deck_id=?",
            (token_id, deck_id),
        )
        self.conn.commit()

    # events ----------------------------------------------------------------
    def insert_events(self, events: list[dict], force_replay: bool) -> dict:
        accepted, duplicates = 0, 0
        for ev in events:
            replay = bool(ev.get("replay")) or force_replay
            ev = {**ev, "replay": replay}
            kind = ev.get("kind")
            if ev["type"] in ("ordering", "duel") and not kind:
                kind = ",".join(ev.get("kinds", []))
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO events (event_id, type, persona, exec_id, deck_id, hand_id,"
                " card_id, kind, replay, ts, payload_json, received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ev["event_id"], ev["type"], ev["persona"], ev["exec_id"], ev["deck_id"],
                 ev.get("hand_id", ""), ev.get("card_id"), kind, int(replay), ev.get("ts", ""),
                 json.dumps(ev), time.time()),
            )
            if cur.rowcount:
                accepted += 1
            else:
                duplicates += 1
        self.conn.commit()
        return {"accepted": accepted, "duplicates": duplicates}

    def distinct_first_play_swipes(self, exec_id: str, deck_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT card_id) c FROM events"
            " WHERE type='swipe' AND exec_id=? AND deck_id=? AND replay=0",
            (exec_id, deck_id),
        ).fetchone()
        return row["c"]

    def events_for_deck(self, deck_id: str, types: tuple[str, ...] = ("swipe", "ordering", "super_like", "duel")) -> list[dict]:
        qmarks = ",".join("?" * len(types))
        rows = self.conn.execute(
            f"SELECT payload_json FROM events WHERE deck_id=? AND type IN ({qmarks})",
            (deck_id, *types),
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def events_for_client(self, client: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT e.payload_json FROM events e JOIN decks d ON e.deck_id=d.deck_id WHERE d.client=?",
            (client,),
        ).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def execs_on_deck(self, deck_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT exec_id FROM events WHERE deck_id=? AND type='swipe' AND replay=0",
            (deck_id,),
        ).fetchall()
        return [r["exec_id"] for r in rows]
