"""House rules, mechanically enforced: the chrome can gamble, the card cannot.

app.js (every render path and all game logic) must never reference the hidden
system fields. The two sanctioned exceptions live in order.js, outside every
render path: the salt-spread in display ordering (mirrors the press) and the
aggregate-only payout reveal (cleanRun). Nothing anywhere touches our_score
or our_components client-side.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _code_only(src: str) -> str:
    """Strip JS comments: the rule binds code, not the comment explaining it."""
    return re.sub(r"//[^\n]*", "", src)


def test_app_js_never_touches_hidden_fields():
    src = _code_only((APP / "app.js").read_text())
    for forbidden in ("our_score", "our_components", "salt", "near_miss"):
        assert forbidden not in src, f"app.js references hidden field: {forbidden}"


def test_no_file_renders_score_or_components():
    for f in APP.glob("*.js"):
        src = f.read_text()
        assert "our_score" not in src, f"{f.name} references our_score"
        assert "our_components" not in src, f"{f.name} references our_components"
    for f in (APP / "index.html", APP / "styles.css"):
        src = f.read_text()
        assert "our_score" not in src and "salt" not in src


def test_order_js_salt_use_is_ordering_and_aggregate_only():
    src = (APP / "order.js").read_text()
    assert "spreadSalt" in src and "cleanRun" in src
    # No DOM access in order.js: it computes, it never renders.
    for dom_token in ("document.", "innerHTML", "getElementById", "createElement"):
        assert dom_token not in src, f"order.js must never touch the DOM ({dom_token})"


def test_chips_pay_identically_for_both_directions():
    src = (APP / "app.js").read_text()
    # bankChips takes no direction argument and is called once per swipe commit.
    assert "function bankChips()" in src
    assert "bankChips(direction" not in src


def test_event_fields_complete():
    src = (APP / "app.js").read_text()
    for field in ("swipe_distance", "swipe_ms", "swipe_velocity", "intensity_bin",
                  "position_in_hand", "position_in_deck", "streak_at_swipe",
                  "session_minute", "since_bonus_event", "muted", "overlap", "retest",
                  "sampling_reason", "ranked_card_ids", "mode: 'immediate'", "mode: 'retroactive'"):
        assert field in src, f"telemetry field missing from app.js: {field}"


def test_share_tile_carries_no_card_contents():
    src = (APP / "app.js").read_text()
    tile = src.split("function drawShareTile")[1].split("\n}")[0]
    for leak in ("title", "agency", "basis", "dollars", "incumbent"):
        assert f"card.{leak}" not in tile and f"c.{leak}" not in tile
