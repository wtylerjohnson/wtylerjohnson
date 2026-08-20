from pathlib import Path

from lila import config
from lila.model import labels as L
from lila.model.features import FEATURE_ALLOWLIST, FORBIDDEN_FEATURES
from lila.model.train import fit_fallback_weights

ROOT = Path(__file__).resolve().parents[2]


def _swipe(exec_id, card_id, direction, dist, ms_on=1500, pos=0):
    return {"exec_id": exec_id, "persona": "fed_vp", "deck_id": "d1", "card_id": card_id,
            "direction": direction, "swipe_distance": dist, "ms_on_card": ms_on,
            "position_in_deck": pos}


def test_labels_normalized_per_exec():
    # exec A swipes big, exec B swipes small; normalization must equalize them
    swipes = [
        _swipe("a", "c1", "right", 1.2), _swipe("a", "c2", "right", 0.6),
        _swipe("a", "c3", "left", -1.2), _swipe("a", "c4", "left", -0.6),
        _swipe("b", "c1", "right", 0.5), _swipe("b", "c2", "right", 0.31),
        _swipe("b", "c3", "left", -0.5), _swipe("b", "c4", "left", -0.31),
    ]
    labels = L.derive_labels(swipes, [])
    assert labels[("a", "fed_vp", "d1", "c1")] == 3
    assert labels[("a", "fed_vp", "d1", "c2")] == 2
    assert labels[("a", "fed_vp", "d1", "c3")] == 0
    assert labels[("a", "fed_vp", "d1", "c4")] == 1
    # exec b's small-but-relatively-strong swipes get the same treatment
    assert labels[("b", "fed_vp", "d1", "c1")] == 3
    assert labels[("b", "fed_vp", "d1", "c4")] == 1


def test_super_like_is_four():
    swipes = [_swipe("a", "c1", "right", 0.9), _swipe("a", "c2", "right", 0.3)]
    sl = [{"exec_id": "a", "persona": "fed_vp", "deck_id": "d1", "card_id": "c1", "mode": "immediate"}]
    labels = L.derive_labels(swipes, sl)
    assert labels[("a", "fed_vp", "d1", "c1")] == 4


def test_salt_gate_sample_aware():
    few = [{"direction": "right"}] * 3  # missed all three, but below minimum
    r = L.salt_gate(few)
    assert not r["quarantine"] and "below minimum" in r["reason"]

    many_bad = [{"direction": "right"}] * 8 + [{"direction": "left"}] * 2
    r = L.salt_gate(many_bad)
    assert r["quarantine"], "20 percent catch over 10 salt judgments must quarantine"

    many_good = [{"direction": "left"}] * 9 + [{"direction": "right"}] * 1
    r = L.salt_gate(many_good)
    assert not r["quarantine"]


def test_rapid_fire_detection():
    fast = [_swipe("a", f"c{i}", "left", -0.5, ms_on=300, pos=i) for i in range(6)]
    slow = [_swipe("a", f"d{i}", "left", -0.5, ms_on=2000, pos=10 + i) for i in range(3)]
    runs = L.rapid_fire_runs(fast + slow)
    assert len(runs) == 1 and runs[0]["length"] == 6
    assert not L.rapid_fire_runs(slow)


def test_pairs_and_metrics():
    orderings = [{"exec_id": "a", "persona": "fed_vp", "deck_id": "d1",
                  "ranked_card_ids": ["c1", "c2", "c3"]}]
    duels = [{"exec_id": "a", "persona": "fed_vp", "deck_id": "d1",
              "card_a": "c2", "card_b": "c3", "winner": "c3"}]
    pairs = L.pairs_from_orderings(orderings) + L.pairs_from_duels(duels)
    scores = {"c1": 0.9, "c2": 0.5, "c3": 0.7}
    acc = L.pairwise_accuracy(pairs, scores)
    assert acc is not None and 0 < acc < 1
    assert L.ndcg_at_k(["c1", "c2"], {"c1": 3, "c2": 1}, 10) == 1.0
    assert L.top_k_overlap(["a", "b", "c"], ["c", "d", "a"], 3) == 2


def test_salt_is_never_a_feature():
    for f in FORBIDDEN_FEATURES:
        assert all(f not in name for name in FEATURE_ALLOWLIST), \
            f"forbidden field {f} leaked into the feature allowlist"


def test_fallback_reproduces_hand_weights_at_zero_labels():
    w = fit_fallback_weights({}, {})
    assert w == config.HAND_WEIGHTS


def test_fallback_stays_near_prior_at_small_n(fixture_pool, pressed_deck):
    decks = {pressed_deck["deck_id"]: pressed_deck}
    labels = {}
    for i, c in enumerate(pressed_deck["cards"][:10]):
        labels[("a", "fed_vp", pressed_deck["deck_id"], c["id"])] = 3 if i % 2 else 0
    w = fit_fallback_weights(decks, labels)
    for k in config.COMPONENT_KEYS:
        assert abs(w[k] - config.HAND_WEIGHTS[k]) < 0.10, \
            "40-swipe regime must not relearn unconstrained weights"


def test_monitor_refuses_promotion_for_insufficient_labels():
    from lila.model.monitor import check_label_volume
    labels = {("a", "fed_vp", "d1", f"c{i}"): 2 for i in range(40)}
    result = check_label_volume(labels)
    assert not result["pass"]
    assert "insufficient labels" in result["detail"]
    assert "not allowed to change the client artifact" in result["detail"]


def test_casino_bias_check_flags_direction_push():
    from lila.model.monitor import check_casino_bias
    low = [{"direction": "left", "streak_at_swipe": 1, "since_bonus_event": 5} for _ in range(25)]
    high = [{"direction": "right", "streak_at_swipe": 15, "since_bonus_event": 5} for _ in range(25)]
    r = check_casino_bias(low + high)
    assert not r["pass"] and r["findings"][0]["mechanic"] == "streak"
    balanced = [{"direction": "right" if i % 2 else "left", "streak_at_swipe": i % 20,
                 "since_bonus_event": i % 12} for i in range(100)]
    assert check_casino_bias(balanced)["pass"]
