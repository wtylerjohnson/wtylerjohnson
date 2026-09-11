import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("LILA_SIGNING_KEY", "test-key-never-committed")

from lila.deck import deck_press, pool_build  # noqa: E402


@pytest.fixture(scope="session")
def fixture_pool(tmp_path_factory):
    src = json.loads((ROOT / "lila" / "fixtures" / "fixture_source_rows.json").read_text())
    from datetime import date
    rows = [pool_build.build_row(s, "varonis", date(2026, 8, 20), "hash32") for s in src]
    return {"client": "varonis", "built_at": "2026-08-20", "fixture": True,
            "embed_model": "hash32:v1", "rows": rows}


@pytest.fixture()
def persona():
    return json.loads((ROOT / "lila" / "personas" / "fed_vp.json").read_text())


@pytest.fixture()
def pressed_deck(fixture_pool, persona):
    return deck_press.press(fixture_pool, persona, "v1", 20, 0.33, [], 0)
