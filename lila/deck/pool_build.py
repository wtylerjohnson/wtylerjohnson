"""pool_build.py <client>: build the candidate pool, wider than the report keeps.

Real mode (inside federal-sales-os, run locally; the store is git-ignored):
  reads data/state/varonis_rows_<date>.json and data/state/notice_store/notices.db,
  reruns the keep filters to harvest authentic near-misses with rejection reasons,
  and extracts the basis sentence from notice description text.

Fixture mode (--fixture): reads lila/fixtures/fixture_source_rows.json, the
deterministic dev pool. Every fixture row is marked and can never be minted
into a real executive link.

Every row gets: kind, recomputed days_remaining, basis (max 160 chars, word
boundary), six derived components in [0,1] with raw inputs retained under
original key names, hidden our_score, sentence embedding, receipts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lila import config
from lila.deck import common


def truncate_basis(sentence: str) -> str:
    s = " ".join((sentence or "").split())
    if len(s) <= config.BASIS_MAX_CHARS:
        return s
    cut = s[: config.BASIS_MAX_CHARS - 3]
    cut = cut.rsplit(" ", 1)[0]
    return cut + "..."


def derive_kind(row: dict) -> str:
    if row.get("kind_hint"):
        return row["kind_hint"]
    nt = (row.get("notice_type") or "").lower()
    status = (row.get("status") or "").lower()
    if row.get("near_miss_reason"):
        return "near_miss"
    if nt == "award notice":
        return "rival_award"
    if nt == "forecast" or row.get("forecast_quarter"):
        return "forecast"
    if nt == "rfq":
        return "rfq"
    if nt in ("sources sought", "request for information") and status == "closed":
        return "closed_rfi"
    return "notice"


def clock_for(row: dict, kind: str, build_date: date) -> dict:
    if kind == "rival_award":
        d, label = row.get("pop_end"), "PoP ends"
    elif kind == "forecast":
        return {"date": None, "label": "forecast qtr", "days_remaining": None,
                "quarter": row.get("forecast_quarter")}
    elif kind == "closed_rfi" or (row.get("status") or "").lower() == "closed":
        d, label = row.get("response_due"), "closed"
    else:
        d, label = row.get("response_due"), "responses due"
    days = None
    if d:
        days = (date.fromisoformat(d) - build_date).days
    return {"date": d, "label": label, "days_remaining": days}


def build_row(src: dict, client: str, build_date: date, embed_provider: str) -> dict:
    kind = derive_kind(src)
    clock = clock_for(src, kind, build_date)
    comp_input = {
        "status": src.get("status"), "kind": kind, "tier": src.get("tier"),
        "set_aside": src.get("set_aside"), "leverage_rank": src.get("leverage_rank"),
        "contact_present": bool(src.get("contact_present")),
        "vehicle": src.get("vehicle"), "dollars": src.get("dollars"),
    }
    components = common.derive_components(comp_input, clock["days_remaining"])
    basis = truncate_basis(src.get("description_sentence") or src.get("title") or "")
    vec, model_id = common.embed_sentence(basis, embed_provider)
    salt = kind == "near_miss"
    return {
        "id": src.get("notice_id") or src.get("record_id"),
        "client": client,
        "kind": kind,
        "seal_key": src.get("seal_key") or "generic",
        "agency": src.get("agency") or "",
        "office": src.get("office") or "",
        "title": src.get("title") or "",
        "basis": basis,
        "clock": clock,
        "dollars": src.get("dollars"),
        "incumbent": src.get("incumbent"),
        "contact_present": bool(src.get("contact_present")),
        "source_url": src.get("sam_url") or src.get("source_url") or "",
        "our_score": common.hand_score(components),
        "our_components": components,
        "raw_inputs": {
            k: src.get(k)
            for k in ("status", "tier", "leverage_rank", "posted", "response_due",
                      "pop_end", "forecast_quarter", "set_aside", "vehicle", "dollars",
                      "naics", "psc", "sol_number", "notice_type", "matched_term",
                      "all_matched_terms", "source")
            if k in src
        },
        "salt": salt,
        "near_miss_reason": src.get("near_miss_reason"),
        "selection_reason": None if salt else (src.get("selection_reason") or f"kept: tier {src.get('tier')} vocabulary match"),
        "rejection_reason": src.get("rejection_reason") if salt else None,
        "overlap": False,
        "retest": False,
        "retrieved_at": src.get("retrieved_at"),
        "sentence_vec": vec,
        "embed_model": model_id,
        "fixture": bool(src.get("fixture")),
    }


def load_fixture_rows() -> list[dict]:
    p = ROOT / "lila" / "fixtures" / "fixture_source_rows.json"
    if not p.exists():
        raise SystemExit("fixture source rows missing: run lila/fixtures/make_fixture_pool.py first")
    return json.loads(p.read_text())


def load_real_rows(client: str) -> list[dict]:
    """Real mode: requires the federal-sales-os checkout with data/state present.
    Reads the client materialization plus the near-miss rerun over notices.db.
    Untestable in the satellite repo; the guarded paths and the row contract
    match the fixture path exactly."""
    state = Path("data/state")
    if not state.exists():
        raise SystemExit(
            "data/state/ not found. Real mode runs inside federal-sales-os with the "
            "git-ignored store present. Use --fixture for the dev pool."
        )
    mats = sorted(state.glob(f"{client}_rows_*.json"))
    if not mats:
        raise SystemExit(f"no {client} materialization under data/state/")
    rows = json.loads(mats[-1].read_text())
    # Near-miss harvest: rerun the keep filters over notices.db, recording
    # rejection_reason per row. Implemented against the real schema when this
    # lands in federal-sales-os; the fixture path exercises the same contract.
    raise SystemExit(
        f"loaded {len(rows)} materialized rows; near-miss filter rerun requires "
        "the FSOS filter module. Wire pool_build.load_real_rows to it on transplant."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("client")
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--build-date", default=None, help="YYYY-MM-DD; pin for reproducibility")
    ap.add_argument("--embed-provider", default="hash32", choices=["hash32", "minilm"])
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "decks"))
    args = ap.parse_args()

    build_date = date.fromisoformat(args.build_date) if args.build_date else date.today()
    src_rows = load_fixture_rows() if args.fixture else load_real_rows(args.client)

    rows = [build_row(s, args.client, build_date, args.embed_provider) for s in src_rows]

    n = len(rows)
    if not args.fixture:
        if n < config.POOL_MIN_ROWS:
            raise SystemExit(f"pool too small: {n} rows, minimum {config.POOL_MIN_ROWS}")

    counts: dict[str, int] = {}
    nm_counts: dict[str, int] = {}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        if r["salt"]:
            nm_counts[r["near_miss_reason"]] = nm_counts.get(r["near_miss_reason"], 0) + 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pool = {
        "client": args.client,
        "built_at": build_date.isoformat(),
        "fixture": args.fixture,
        "embed_model": rows[0]["embed_model"] if rows else None,
        "rows": rows,
    }
    pool_path = out_dir / f"pool_{args.client}_{build_date.isoformat()}.json"
    pool_path.write_text(common.canonical_json(pool) + "\n")

    receipt = {
        "artifact": pool_path.name,
        "pool_hash": common.content_id(pool),
        "client": args.client,
        "built_at": build_date.isoformat(),
        "fixture": args.fixture,
        "row_count": n,
        "counts_by_kind": counts,
        "near_miss_by_reason": nm_counts,
        "below_target": n < config.POOL_TARGET_LOW,
        "embed_model": pool["embed_model"],
        "component_derivation": "v1 (placeholder keys pending FSOS docs reconciliation)",
    }
    receipt_path = out_dir / f"pool_{args.client}_{build_date.isoformat()}.receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    print(f"pool: {n} rows -> {pool_path}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    if args.fixture:
        print("FIXTURE POOL: never mint real executive links from this pool.")


if __name__ == "__main__":
    main()
