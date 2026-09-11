import json
from pathlib import Path

from lila import config
from lila.deck import common, deck_press

ROOT = Path(__file__).resolve().parents[2]


def test_real_fixture_row_builds_valid_card(fixture_pool):
    real = next(r for r in fixture_pool["rows"] if r["id"].startswith("b2a14fde"))
    schema = json.loads((ROOT / "lila" / "schema" / "card.json").read_text())
    for field in schema["required"]:
        assert field in real, f"missing required card field: {field}"
    assert len(real["basis"]) <= config.BASIS_MAX_CHARS
    for k in config.COMPONENT_KEYS:
        assert 0.0 <= real["our_components"][k] <= 1.0
    assert real["kind"] == "notice"
    assert real["source_url"].startswith("https://sam.gov/opp/")
    # raw source keys preserved, never renamed
    assert real["raw_inputs"]["status"] == "open"
    assert real["raw_inputs"]["tier"] == 2
    assert real["raw_inputs"]["leverage_rank"] == 1


def test_days_remaining_recomputed_not_trusted(fixture_pool):
    real = next(r for r in fixture_pool["rows"] if r["id"].startswith("b2a14fde"))
    # response_due 2026-08-25 minus build date 2026-08-20
    assert real["clock"]["days_remaining"] == 5


def test_press_is_deterministic(fixture_pool, persona):
    a = deck_press.press(fixture_pool, persona, "v1", 20, 0.33, [], 0)
    b = deck_press.press(fixture_pool, persona, "v1", 20, 0.33, [], 0)
    assert common.canonical_json(a) == common.canonical_json(b)
    assert a["deck_id"] == b["deck_id"]


def test_overlap_shared_across_personas_and_flagged(fixture_pool, persona):
    import json as j
    p2 = j.loads((ROOT / "lila" / "personas" / "oem_ae.json").read_text())
    a = deck_press.press(fixture_pool, persona, "v1", 20, 0.33, [], 0)
    b = deck_press.press(fixture_pool, p2, "v1", 20, 0.33, [], 0)
    ov_a = {c["id"] for c in a["cards"] if c["overlap"]}
    ov_b = {c["id"] for c in b["cards"] if c["overlap"]}
    assert ov_a == ov_b
    assert len(ov_a) == round(20 * config.OVERLAP_RATIO)
    ids_b = {c["id"] for c in b["cards"]}
    assert ov_a <= ids_b


def test_salt_ratio_and_authenticity(pressed_deck):
    salt = [c for c in pressed_deck["cards"] if c["salt"]]
    assert len(salt) == round(20 * 0.33)
    for c in salt:
        assert c["kind"] == "near_miss"
        assert c["near_miss_reason"] in config.NEAR_MISS_REASONS
        assert c["rejection_reason"]


def test_display_order_per_exec(pressed_deck):
    cs = pressed_deck["card_set_seed"]
    s1 = common.display_order_seed(cs, "exec-one", "fed_vp")
    s2 = common.display_order_seed(cs, "exec-two", "fed_vp")
    o1 = [c["id"] for c in common.display_order(s1, pressed_deck["cards"])]
    o1_again = [c["id"] for c in common.display_order(s1, pressed_deck["cards"])]
    o2 = [c["id"] for c in common.display_order(s2, pressed_deck["cards"])]
    assert o1 == o1_again, "same exec must replay the same order"
    assert o1 != o2, "different execs must see different orders"
    assert sorted(o1) == sorted(o2), "same card set"


def test_salt_never_adjacent_when_avoidable(pressed_deck):
    cs = pressed_deck["card_set_seed"]
    for exec_id in ("a", "b", "c", "d"):
        seed = common.display_order_seed(cs, exec_id, "fed_vp")
        ordered = common.display_order(seed, pressed_deck["cards"])
        for i in range(1, len(ordered) - 1):
            if ordered[i]["salt"] and ordered[i - 1]["salt"]:
                remaining = ordered[i + 1:]
                assert all(c["salt"] for c in remaining), "adjacent salt while non-salt remained"


def test_hand_sizes_scale():
    assert deck_press.hand_sizes_for(50) == [15, 15, 20]
    assert sum(deck_press.hand_sizes_for(20)) == 20
    assert sum(deck_press.hand_sizes_for(100)) == 100


def test_retest_rides_inside_overlap_budget(fixture_pool, persona):
    non_salt_ids = [r["id"] for r in fixture_pool["rows"] if not r["salt"]]
    retest = non_salt_ids[:2]
    deck = deck_press.press(fixture_pool, persona, "v2", 20, 0.15, retest, 0)
    retested = [c for c in deck["cards"] if c["retest"]]
    assert retested, "retest ids present in pool must appear"
    for c in retested:
        assert c["overlap"], "retest cards ride inside the overlap budget"
