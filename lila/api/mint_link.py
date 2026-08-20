"""mint_link.py <deck_file> --exec-name "..." : mint a signed URL for one exec.

The mint is the per-executive point: it selects the calibration vs standard
variant by the exec's play history, computes display_order_seed per the locked
recipe, records the mint receipt (order seed AND resulting positions), loads
the deck into the store, and prints the full URL. Tyler sends it personally;
that printed URL is the whole delivery system for v1.

Guard: decks pressed from a fixture pool are refused without --dev. Fixture
rows must never reach a real executive.

Link format: {app_base}/#t={token}. The token rides in the URL fragment so it
never appears in server logs; the app reads it, verifies nothing (the API
does), and fetches GET /decks/{deck_id}.
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


def mint_for_exec(deck: dict, exec_id: str, exec_name: str | None, store: Store,
                  exp_days: int = config.TOKEN_TTL_DAYS) -> tuple[str, dict]:
    do_seed = common.display_order_seed(deck["card_set_seed"], exec_id, deck["persona"])
    ordered = common.display_order(do_seed, deck["cards"])
    positions = [c["id"] for c in ordered]

    payload = {
        "deck_id": deck["deck_id"],
        "exec_id": exec_id,
        "persona": deck["persona"],
        "client": deck["client"],
        "display_order_seed": do_seed,
        "variant": deck["variant"],
        "exp": int(time.time()) + exp_days * 86400,
    }
    token = tokens.mint(payload)
    token_id = token.split(".")[1][:32]

    store.put_deck(deck)
    store.put_token({
        "token_id": token_id,
        "exec_id": exec_id,
        "exec_name": exec_name,
        "deck_id": deck["deck_id"],
        "client": deck["client"],
        "persona": deck["persona"],
        "variant": deck["variant"],
        "display_order_seed": do_seed,
        "positions": positions,
    })

    receipt = {
        "minted": "token",
        "deck_id": deck["deck_id"],
        "deck_version": deck["deck_version"],
        "variant": deck["variant"],
        "client": deck["client"],
        "persona": deck["persona"],
        "exec_id": exec_id,
        "display_order_seed": do_seed,
        "positions": positions,
        "hands": deck["hands"],
        "fixture": deck.get("pool_fixture", False),
    }
    return token, receipt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_file")
    ap.add_argument("--exec-name", default=None, help="display name the exec chose; the only PII, lives in tokens only")
    ap.add_argument("--exec-id", default=None, help="opaque id; generated if omitted; NEVER a name or email")
    ap.add_argument("--db", default=os.environ.get("LILA_DB", str(ROOT / "lila" / "api" / "lila.db")))
    ap.add_argument("--app-base", default=os.environ.get("LILA_APP_BASE", "http://localhost:8080"))
    ap.add_argument("--api-base", default=os.environ.get("LILA_API_BASE"),
                    help="append &api= to the link when the API is not the app origin")
    ap.add_argument("--dev", action="store_true", help="allow fixture decks (development only)")
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "decks"))
    args = ap.parse_args()

    deck = json.loads(Path(args.deck_file).read_text())
    if deck.get("pool_fixture") and not args.dev:
        raise SystemExit("REFUSED: this deck was pressed from a FIXTURE pool. "
                         "Fixture rows never reach a real executive. Use --dev for development links.")

    exec_id = args.exec_id or ("x" + secrets.token_hex(8))
    store = Store(args.db)

    history = store.exec_history_count(exec_id, deck["client"])
    expected = "calibration" if history == 0 else "standard"
    if deck["variant"] != expected:
        print(f"note: exec history suggests the {expected} variant "
              f"(prior decks for this client: {history}); minting {deck['variant']} as given.")

    token, receipt = mint_for_exec(deck, exec_id, args.exec_name, store)
    out = Path(args.out_dir) / f"mint_{deck['deck_id']}_{exec_id}.receipt.json"
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    api_suffix = f"&api={args.api_base}" if args.api_base else ""
    print(f"exec_id: {exec_id}")
    print(f"receipt: {out}")
    print(f"link:    {args.app_base}/#t={token}{api_suffix}")


if __name__ == "__main__":
    main()
