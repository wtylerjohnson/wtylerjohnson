"""deck_press.py <client> --persona <slug> --deck-version <v> --n 50 --salt 0.15|0.33

Presses a deterministic CARD SET. Display order is per executive and is
applied at mint (lila/api/mint_link.py) and in the app, from
display_order_seed; the press knows nothing about executives.

Seed recipe (locked):
  card_set_seed     = hash(client, persona, deck_version)
  display_order_seed = hash(card_set_seed, opaque_subject_id, persona)

Sampling: stratified by kind from the pool's own non-salt distribution with a
rival_award cap and per-kind floors; salt layered at the given ratio; the
cross-persona overlap set (OVERLAP_RATIO) derives from client and deck_version
only, so any two personas of the same deck version share exactly that set.
Retest cards (model-crowd disagreement) occupy overlap slots first, capped at
RETEST_MAX_SHARE. Byte-identical on re-press: no wall clock anywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lila import config
from lila.deck import common

DEALER_LINES = [
    "Fresh shoe.",
    "The table is hot.",
    "Heads-up round.",
    "House keeps the receipts.",
    "Last hand before the break.",
    "New table, same rules.",
    "The clock is the house edge.",
    "Stack them how you would call them.",
]


def hand_sizes_for(n: int) -> list[int]:
    base = config.HAND_SIZES
    total = sum(base)
    sizes = [max(1, round(n * b / total)) for b in base]
    sizes[-1] += n - sum(sizes)
    return sizes


def largest_remainder(targets: dict[str, float], slots: int) -> dict[str, int]:
    raw = {k: v * slots for k, v in targets.items()}
    alloc = {k: int(v) for k, v in raw.items()}
    remaining = slots - sum(alloc.values())
    for k in sorted(raw, key=lambda k: (raw[k] - alloc[k], k), reverse=True)[:remaining]:
        alloc[k] += 1
    return alloc


def strata_targets(non_salt: list[dict]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for r in non_salt:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    total = sum(counts.values()) or 1
    props = {k: v / total for k, v in counts.items()}
    if props.get("rival_award", 0) > config.RIVAL_AWARD_MAX_SHARE:
        props["rival_award"] = config.RIVAL_AWARD_MAX_SHARE
    for kind, floor in config.KIND_FLOOR.items():
        if kind in props and props[kind] < floor:
            props[kind] = floor
    s = sum(props.values())
    return {k: v / s for k, v in props.items()}


def press(pool: dict, persona: dict, deck_version: str, n: int, salt_ratio: float,
          retest_ids: list[str], prior_exec_count: int) -> dict:
    client = pool["client"]
    cs_seed = common.card_set_seed(client, persona["slug"], deck_version)
    overlap_seed = common.stable_hash_hex(client, deck_version, "overlap")

    rows = {r["id"]: r for r in pool["rows"]}
    salt_pool = [r for r in pool["rows"] if r["salt"]]
    non_salt = [r for r in pool["rows"] if not r["salt"]]

    n_salt = round(n * salt_ratio)
    n_non = n - n_salt
    n_overlap = min(round(n * config.OVERLAP_RATIO), n_non)
    n_retest_cap = round(n * config.RETEST_MAX_SHARE)

    # Overlap set: shared across personas of this deck version. Retest ids
    # (authentic pool rows flagged by the monitor) take overlap slots first.
    retest_in_pool = [i for i in common.hash_order(overlap_seed, retest_ids) if i in rows][:n_retest_cap]
    remaining_overlap = n_overlap - len(retest_in_pool)
    overlap_rest = [i for i in common.hash_order(overlap_seed, [r["id"] for r in non_salt])
                    if i not in retest_in_pool][:max(0, remaining_overlap)]
    overlap_ids = set(retest_in_pool) | set(overlap_rest)

    # Stratified persona remainder from card_set_seed.
    targets = strata_targets(non_salt)
    alloc = largest_remainder(targets, n_non)
    chosen: list[str] = list(overlap_ids)
    for kind in sorted(alloc):
        have = sum(1 for i in chosen if rows[i]["kind"] == kind)
        need = max(0, alloc[kind] - have)
        candidates = [r["id"] for r in non_salt if r["kind"] == kind and r["id"] not in overlap_ids]
        chosen += common.hash_order(cs_seed, candidates)[:need]
    if len(chosen) < n_non:  # top up across kinds if a stratum ran dry
        rest = [r["id"] for r in non_salt if r["id"] not in set(chosen)]
        chosen += common.hash_order(cs_seed, rest)[: n_non - len(chosen)]
    chosen = chosen[:n_non]

    salt_ids = common.hash_order(common.stable_hash_hex(cs_seed, "salt"),
                                 [r["id"] for r in salt_pool])[:n_salt]

    cards = []
    for cid in sorted(set(chosen) | set(salt_ids)):
        c = dict(rows[cid])
        c["overlap"] = cid in overlap_ids
        c["retest"] = cid in set(retest_in_pool)
        cards.append(c)

    line_start = int(common.stable_hash_hex(cs_seed, "dealer")[:8], 16) % len(DEALER_LINES)
    dealer_lines = DEALER_LINES[line_start:] + DEALER_LINES[:line_start]

    deck = {
        "client": client,
        "persona": persona["slug"],
        "display_name": persona["display_name"],
        "role_line": persona["role_line"],
        "deck_version": deck_version,
        "variant": "calibration" if salt_ratio >= 0.25 else "standard",
        "card_set_seed": cs_seed,
        "pressed_from_pool": pool["built_at"],
        "pool_fixture": pool.get("fixture", False),
        "n": len(cards),
        "salt_ratio": salt_ratio,
        "hands": hand_sizes_for(len(cards)),
        "table": {
            "dealer_lines": dealer_lines,
            "flair_tiers": [5, 10, 20],
            "bonus_interval": {"min": 10, "max": 14},
            "duels_per_hand": config.DUELS_PER_HAND,
            "duel_pairs": [],
            "prior_exec_count": prior_exec_count,
        },
        "cards": cards,
    }
    deck["deck_id"] = common.content_id(deck)
    return deck


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("client")
    ap.add_argument("--persona", required=True)
    ap.add_argument("--deck-version", default="v1")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--salt", type=float, default=config.SALT_RATIO)
    ap.add_argument("--pool", default=None, help="pool json path; defaults to newest for client")
    ap.add_argument("--retest-file", default=None, help="json list of card ids from the monitor")
    ap.add_argument("--prior-execs", type=int, default=0)
    ap.add_argument("--out-dir", default=str(ROOT / "lila" / "decks"))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    pool_candidates = [p for p in sorted(out_dir.glob(f"pool_{args.client}_*.json"))
                       if not p.name.endswith(".receipt.json")]
    pool_path = Path(args.pool) if args.pool else pool_candidates[-1]
    pool = json.loads(pool_path.read_text())

    persona_path = ROOT / "lila" / "personas" / f"{args.persona}.json"
    persona = json.loads(persona_path.read_text())
    retest_ids = json.loads(Path(args.retest_file).read_text()) if args.retest_file else []

    deck = press(pool, persona, args.deck_version, args.n, args.salt, retest_ids, args.prior_execs)

    name = f"deck_{args.client}_{args.persona}_{args.deck_version}_{deck['variant']}"
    deck_path = out_dir / f"{name}.json"
    deck_path.write_text(common.canonical_json(deck) + "\n")

    counts: dict[str, int] = {}
    for c in deck["cards"]:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    receipt = {
        "artifact": deck_path.name,
        "deck_id": deck["deck_id"],
        "card_set_seed": deck["card_set_seed"],
        "pool_file": pool_path.name,
        "pool_hash": common.content_id(pool),
        "variant": deck["variant"],
        "n": deck["n"],
        "counts_by_kind": counts,
        "salt_count": sum(1 for c in deck["cards"] if c["salt"]),
        "overlap_count": sum(1 for c in deck["cards"] if c["overlap"]),
        "retest_count": sum(1 for c in deck["cards"] if c["retest"]),
        "hands": deck["hands"],
        "fixture": deck["pool_fixture"],
    }
    (out_dir / f"{name}.receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    print(f"deck {deck['deck_id']} -> {deck_path}")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
