"""Shared deterministic primitives for the LILA deck pipeline.

Everything here must be reproducible: no wall clock, no dict-order dependence,
no random state outside seeded generators. The display-order algorithm is
mirrored byte-for-byte in the app (lila/app/order.js); change both or neither.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lila import config


def stable_hash_hex(*parts: str) -> str:
    """sha256 over colon-joined parts, hex. The one hashing primitive."""
    joined = ":".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def card_set_seed(client: str, persona: str, deck_version: str) -> str:
    """Locked recipe: card_set_seed = hash(client, persona, deck_version)."""
    return stable_hash_hex(client, persona, deck_version)


def display_order_seed(cs_seed: str, opaque_subject_id: str, persona: str) -> str:
    """Locked recipe: display_order_seed = hash(card_set_seed, opaque_subject_id, persona).

    Never pass a name or email as opaque_subject_id."""
    return stable_hash_hex(cs_seed, opaque_subject_id, persona)


def hash_order(seed_hex: str, ids: list[str]) -> list[str]:
    """Language-agnostic deterministic permutation: sort ids by
    sha256(seed || ":" || id). Identical implementation in the app."""
    return sorted(ids, key=lambda i: stable_hash_hex(seed_hex, i))


def spread_salt(cards: list[dict]) -> list[dict]:
    """Deterministic post-pass: no two salt cards adjacent when avoidable.
    Mirrored in lila/app/order.js; keep trivially simple."""
    cards = list(cards)
    i = 1
    while i < len(cards):
        if cards[i]["salt"] and cards[i - 1]["salt"]:
            j = i + 1
            while j < len(cards) and cards[j]["salt"]:
                j += 1
            if j >= len(cards):
                break
            cards[i], cards[j] = cards[j], cards[i]
        i += 1
    return cards


def display_order(do_seed: str, cards: list[dict]) -> list[dict]:
    """Per-exec display order: hash-sort by display_order_seed, then salt spread."""
    by_id = {c["id"]: c for c in cards}
    ordered_ids = hash_order(do_seed, list(by_id.keys()))
    return spread_salt([by_id[i] for i in ordered_ids])


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_id(obj) -> str:
    """First 12 hex of sha256 over canonical JSON: deck ids, receipt hashes."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Six-component derivation. v1 formulas; keys are placeholders pending FSOS
# docs reconciliation. Raw inputs are always retained on the row so these can
# be re-derived when the canonical sketch lands.
# ---------------------------------------------------------------------------

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def derive_components(row: dict, days_remaining: int | None) -> dict:
    status = (row.get("status") or "").lower()
    kind = row.get("kind", "notice")
    tier = row.get("tier")
    set_aside = (row.get("set_aside") or "").lower()

    if status == "open":
        openness = 1.0
    elif kind == "forecast":
        openness = 0.6
    else:
        openness = 0.15
    if set_aside and "no set aside" not in set_aside:
        openness *= 0.7

    if days_remaining is None:
        clock = 0.4
    elif days_remaining < 0:
        clock = 0.05
    else:
        clock = max(0.05, math.exp(-days_remaining / 60.0))

    tier_map = {1: 1.0, 2: 0.75, 3: 0.45}
    fit_tier = tier_map.get(tier, 0.15)

    lr = row.get("leverage_rank")
    account = 1.0 / math.sqrt(lr) if isinstance(lr, (int, float)) and lr >= 1 else 0.3

    access = 0.7 if row.get("contact_present") else 0.25
    if row.get("vehicle"):
        access += 0.3

    d = row.get("dollars")
    dollars = _clamp01(math.log10(d) / 9.0) if isinstance(d, (int, float)) and d > 0 else 0.2

    return {
        "openness": round(_clamp01(openness), 4),
        "clock": round(_clamp01(clock), 4),
        "fit_tier": round(_clamp01(fit_tier), 4),
        "account": round(_clamp01(account), 4),
        "access": round(_clamp01(access), 4),
        "dollars": round(_clamp01(dollars), 4),
    }


def hand_score(components: dict) -> float:
    return round(sum(config.HAND_WEIGHTS[k] * components[k] for k in config.COMPONENT_KEYS), 6)


# ---------------------------------------------------------------------------
# Embedding provider adapter. The real press uses a locally cached
# all-MiniLM-L6-v2 (or whatever CONVENTIONS standardizes on); the fixture
# pipeline uses a deterministic hash projection so the satellite repo carries
# no model weights. Both record model id and hash in the receipt.
# ---------------------------------------------------------------------------

EMBED_DIM = 32


def embed_sentence(text: str, provider: str = "hash32") -> tuple[list[float], str]:
    if provider == "hash32":
        vec = []
        for i in range(EMBED_DIM):
            h = hashlib.sha256(f"{i}:{text}".encode("utf-8")).digest()
            vec.append(round(int.from_bytes(h[:4], "big") / 2**32 * 2 - 1, 6))
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [round(v / norm, 6) for v in vec], "hash32:v1"
    if provider == "minilm":
        from sentence_transformers import SentenceTransformer  # optional, FSOS press only

        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model.encode([text])[0].tolist(), "all-MiniLM-L6-v2"
    raise ValueError(f"unknown embedding provider: {provider}")


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1.0
    db = math.sqrt(sum(y * y for y in b)) or 1.0
    return num / (da * db)
