"""Feature construction for the ranker. The feature list is a checked-in
allowlist; `salt` is a held-out check and NEVER a feature (tested).

Until the client reaches EMBEDDING_VECTOR_GATE usable labels, the full
sentence vector stays out of LightGBM; three scalar reductions ride instead:
similarity to the client capability-taxonomy centroid, to the exec's own prior
right-swipe centroid (when history exists), and to the client's pooled
right-swipe centroid. The full vector is stored on every row regardless.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lila import config
from lila.deck import common

FEATURE_ALLOWLIST = [
    "openness", "clock", "fit_tier", "account", "access", "dollars",
    "persona_idx", "kind_idx", "tier", "days_remaining", "agency_idx",
    "vehicle_present", "incumbent_flag", "rival_flag", "dollars_bucket",
    "sim_taxonomy", "sim_exec_rights", "sim_client_rights",
]

FORBIDDEN_FEATURES = ["salt", "overlap", "retest", "near_miss_reason"]

_KINDS = {k: i for i, k in enumerate(config.CARD_KINDS)}


def _dollars_bucket(d) -> int:
    if not isinstance(d, (int, float)) or d <= 0:
        return 0
    for i, edge in enumerate([1e5, 5e5, 1e6, 5e6, 1e7, 1e8], start=1):
        if d < edge:
            return i
    return 7


def centroid(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


class FeatureBuilder:
    def __init__(self, decks: dict[str, dict], taxonomy_texts: list[str] | None = None,
                 embed_provider: str = "hash32"):
        self.cards: dict[str, dict] = {}
        for deck in decks.values():
            for c in deck["cards"]:
                self.cards[c["id"]] = c
        agencies = sorted({c["agency"] for c in self.cards.values()})
        self.agency_idx = {a: i for i, a in enumerate(agencies)}
        self.personas = sorted({d["persona"] for d in decks.values()})
        self.persona_idx = {p: i for i, p in enumerate(self.personas)}
        tax_texts = taxonomy_texts or ["data security", "data classification", "insider threat",
                                       "records management", "data access governance"]
        self.tax_centroid = centroid([common.embed_sentence(t, embed_provider)[0] for t in tax_texts])

    def right_centroids(self, labels_map: dict) -> tuple[dict, list[list[float]] | None]:
        per_exec: dict[str, list] = {}
        pooled: list = []
        for (exec_id, _, _, cid), lab in labels_map.items():
            if lab >= 2 and cid in self.cards and self.cards[cid].get("sentence_vec"):
                per_exec.setdefault(exec_id, []).append(self.cards[cid]["sentence_vec"])
                pooled.append(self.cards[cid]["sentence_vec"])
        return ({k: centroid(v) for k, v in per_exec.items()}, centroid(pooled))

    def row(self, card: dict, persona: str, exec_centroid, client_centroid) -> list[float]:
        vec = card.get("sentence_vec")
        sim_tax = common.cosine(vec, self.tax_centroid) if vec and self.tax_centroid else 0.0
        sim_exec = common.cosine(vec, exec_centroid) if vec and exec_centroid else 0.0
        sim_client = common.cosine(vec, client_centroid) if vec and client_centroid else 0.0
        comp = card["our_components"]
        days = card["clock"].get("days_remaining")
        return [
            comp["openness"], comp["clock"], comp["fit_tier"],
            comp["account"], comp["access"], comp["dollars"],
            float(self.persona_idx.get(persona, -1)),
            float(_KINDS.get(card["kind"], -1)),
            float(card["raw_inputs"].get("tier") or 0),
            float(days if days is not None else -999),
            float(self.agency_idx.get(card["agency"], -1)),
            1.0 if card["raw_inputs"].get("vehicle") else 0.0,
            1.0 if card.get("incumbent") else 0.0,
            1.0 if card["kind"] == "rival_award" else 0.0,
            float(_dollars_bucket(card.get("dollars"))),
            sim_tax, sim_exec, sim_client,
        ]
