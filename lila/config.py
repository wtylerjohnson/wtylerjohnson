"""Global v1 constants for LILA SWIPE. One module, no client-specific overrides
until evidence says otherwise (locked decision, 2026-08-20)."""

# Display bin only. Raw gesture is always captured; the final relevance
# mapping lives in training code, never frozen in the browser.
INTENSITY_DISPLAY_THRESHOLD = 0.55

# One overlap budget serving persona consistency AND model-disagreement retesting.
OVERLAP_RATIO = 0.20

# Adaptive salt per exec: calibration first deck, standard after.
SALT_RATIO_FIRST_DECK = 0.33
SALT_RATIO = 0.15

# A 50-card deck plays as three hands.
HAND_SIZES = [15, 15, 20]

DUELS_PER_HAND = 2
DUELS_PER_HAND_MAX = 3

# Pooled-first gating: 300 total labels per client (personas pooled, persona as
# a feature). Persona-specific models gate separately. No cross-client pooling in v1.
CLIENT_LABEL_GATE = 300
PERSONA_LABEL_GATE = 300

# Full sentence vectors stay out of LightGBM until this many usable labels per client.
EMBEDDING_VECTOR_GATE = 1000

# Sample-aware salt quality gate: no quarantine below the minimum count;
# one-sided binomial test against the null rather than a raw percentage.
SALT_MIN_JUDGMENTS = 8
SALT_CATCH_NULL = 0.70
SALT_ALPHA = 0.05

# Rapid-fire signal: runs of this many swipes under this many milliseconds.
RAPID_FIRE_MS = 800
RAPID_FIRE_RUN = 5

# Streak breaks after this idle gap; never breaks on direction.
STREAK_IDLE_MS = 8000

# Retest cards ride inside the overlap budget; cap as share of a deck.
RETEST_MAX_SHARE = 0.10

# Minimum allocation per pursuit kind under adaptive sampling, so decks
# never collapse into notices only. Fractions of non-salt slots.
KIND_FLOOR = {
    "notice": 0.10,
    "rival_award": 0.10,
    "forecast": 0.02,
    "closed_rfi": 0.05,
    "rfq": 0.02,
}

# Cap so the 508 rival awards do not swamp a deck.
RIVAL_AWARD_MAX_SHARE = 0.30

# Hand-authored six-term weights: the hypothesis. The regularized logistic
# fallback is initialized from and shrunk toward these.
HAND_WEIGHTS = {
    "openness": 0.20,
    "clock": 0.20,
    "fit_tier": 0.25,
    "account": 0.15,
    "access": 0.10,
    "dollars": 0.10,
}

COMPONENT_KEYS = ["openness", "clock", "fit_tier", "account", "access", "dollars"]

REASONS_RIGHT = ["fit", "timing", "money", "access"]
REASONS_LEFT = ["wrong category", "too small", "closed or dead", "wrong buyer", "cannot win"]

CARD_KINDS = ["notice", "rival_award", "forecast", "closed_rfi", "rfq", "near_miss"]

NEAR_MISS_REASONS = [
    "vocab_hit_scope_unrelated",
    "expired",
    "out_of_category_shared_terms",
]

EVENT_TYPES = ["swipe", "ordering", "super_like", "duel"]

DUEL_SAMPLING_REASONS = ["recent_rights", "uncertainty_pair", "disagreement"]

# Signed deck tokens: key comes from the environment, never committed.
SIGNING_KEY_ENV = "LILA_SIGNING_KEY"
TOKEN_TTL_DAYS = 14

BASIS_MAX_CHARS = 160
POOL_MIN_ROWS = 150
POOL_TARGET_LOW = 200
POOL_TARGET_HIGH = 400
