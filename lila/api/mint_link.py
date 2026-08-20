"""mint_link.py <deck_file> [<deck_file> ...] --exec-name "..."

One signed URL per executive, carrying EVERY persona deck minted for them.
The exec chooses their seat (persona) inside the app before the first card:
the persona is the point of view of the priority, so it must be self-selected,
never assigned. The choice order itself is signal (seat_index rides on every
event).

The mint remains the per-executive point: it selects the calibration vs
standard variant by play history, computes display_order_seed per persona per
the locked recipe, records the mint receipt (order seed AND positions per
persona), loads the decks into the store, and prints the full URL. Tyler sends
it personally.

Guard: decks pressed from a fixture pool are refused without --dev.

Link format: {app_base}/#t={token}. The token rides in the URL fragment so it
never appears in server logs.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lila import config
from lila.api import tokens
from lila.api.storage import Store
from lila.deck import common


def mint_for_exec(decks: list[dict], exec_id: str, exec_name: str | None, store: Store,
                  exp_days: int = config.TOKEN_TTL_DAYS) -> tuple[str, dict]:
    clients = {d["client"] for d in decks}
    if len(clients) != 1:
        raise ValueError("one link is one exec and one client; mixed clients refused")
    personas_payload: dict = {}
    positions_by_persona: dict = {}
    for deck in decks:
        slug = deck["persona"]
        if slug in personas_payload:
            raise ValueError(f"two decks for persona {slug}; one deck per persona per link")
        do_seed = common.display_order_seed(deck["card_set_seed"], exec_id, slug)
        ordered = common.display_order(do_seed, deck["cards"])
        personas_payload[slug] = {
            "deck_id": deck["deck_id"],
            "display_order_seed": do_seed,
            "display_name": deck["display_name"],
            "variant": deck["variant"],
        }
        positions_by_persona[slug] = [c["id"] for c in ordered]

    payload = {
        "client": decks[0]["client"],
        "exec_id": exec_id,
        "personas": personas_payload,
        "exp": int(time.time()) + exp_days * 86400,
    }
    token = tokens.mint(payload)
    token_id = token.split(".")[1][:32]

    for deck in decks:
        slug = deck["persona"]
        store.put_deck(deck)
        store.put_token({
            "token_id": token_id,
            "exec_id": exec_id,
            "exec_name": exec_name,
            "deck_id": deck["deck_id"],
            "client": deck["client"],
            "persona": slug,
            "variant": deck["variant"],
            "display_order_seed": personas_payload[slug]["display_order_seed"],
            "positions": positions_by_persona[slug],
        })

    receipt = {
        "minted": "token",
        "client": decks[0]["client"],
        "exec_id": exec_id,
        "personas": {
            slug: {
                "deck_id": personas_payload[slug]["deck_id"],
                "deck_version": next(d["deck_version"] for d in decks if d["persona"] == slug),
                "variant": personas_payload[slug]["variant"],
                "display_order_seed": personas_payload[slug]["display_order_seed"],
                "positions": positions_by_persona[slug],
                "hands": next(d["hands"] for d in decks if d["persona"] == slug),
            }
            for slug in personas_payload
        },
        "fixture": any(d.get("pool_fixture") for d in decks),
    }
    return token, receipt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_files", nargs="+", help="one deck per persona; the exec chooses their seat in the app")
    ap.add_argument("--exec-name", default=None, help="display name the exec chose; the only PII, lives in tokens only")
    ap.add_argument("--exec-id", default=None, help="opaque id; generated if omitted; NEVER a name or email")
    ap.add_argument("--db", default=os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    ap.add_argument("--app-base", default=os.environ.get("LILA_APP_BASE", "http://localhost:8080"))
    ap.add_argument("--api-base", default=os.environ.get("LILA_API_BASE"),
                    help="append &api= to the link when the API is not the app origin")
    ap.add_argument("--dev", action="store_true", help="allow fixture decks (development only)")
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "decks"))
    args = ap.parse_args()

    decks = [json.loads(Path(f).read_text()) for f in args.deck_files]
    if any(d.get("pool_fixture") for d in decks) and not args.dev:
        raise SystemExit("REFUSED: at least one deck was pressed from a FIXTURE pool. "
                         "Fixture rows never reach a real executive. Use --dev for development links.")

    exec_id = args.exec_id or ("x" + secrets.token_hex(8))
    store = Store(args.db)

    history = store.exec_history_count(exec_id, decks[0]["client"])
    expected = "calibration" if history == 0 else "standard"
    for d in decks:
        if d["variant"] != expected:
            print(f"note: exec history suggests the {expected} variant for {d['persona']} "
                  f"(prior decks for this client: {history}); minting {d['variant']} as given.")

    token, receipt = mint_for_exec(decks, exec_id, args.exec_name, store)
    deck_ids = "_".join(sorted(p["deck_id"] for p in receipt["personas"].values()))[:40]
    out = Path(args.out_dir) / f"mint_{deck_ids}_{exec_id}.receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    api_suffix = f"&api={args.api_base}" if args.api_base else ""
    print(f"exec_id:  {exec_id}")
    print(f"personas: {', '.join(sorted(receipt['personas']))} (exec chooses their seat in the app)")
    print(f"receipt:  {out}")
    print(f"link:     {args.app_base}/#t={token}{api_suffix}")


if __name__ == "__main__":
    main()
