# LILA SWIPE: build plan for Claude Code

A swipe deck of federal pursuits that executives play on their phones, per persona. Every judgment streams back to a hosted endpoint and trains the ranker that orders the Federal Market Map. Casino-fun on the surface, a labeling instrument underneath.

This document is the execution plan. It is written to be landed by Claude Code in ordered, verifiable steps. Each landing has a definition of done and a prove step. Tyler merges. Worktree branch: `fable/lila-swipe`.

---

## Step zero: reconcile before writing code

This plan was authored without the FSOS repo open. Before landing anything, read these in the FSOS repo and adjust the names in this plan to match exactly what exists:

1. `FSOS_VISION_SPINE.md`: the why. Do not contradict it.
2. `CLAUDE.md` and `CONVENTIONS.md`: naming, receipts format, tooling, lint rules. Where this plan and CONVENTIONS disagree, CONVENTIONS wins.
3. The pursuit-row schema in the current press, 04 band (open, displace, coming, past). The card `kind` field below maps onto that band; confirm the field names and enum values.
4. The six-term score sketch in docs: openness, clock, fit tier, account, access, dollars. Use the exact component keys the docs use. Everywhere this plan says `our_components`, it means those six, by their canonical names.

Band-to-kind mapping (confirm against the press):

| 04 band | card kind |
|---|---|
| open | `notice`, `rfq` |
| displace | `rival_award` |
| coming | `forecast` |
| past | `closed_rfi` |
| (not in band) | `near_miss` (salt only) |

## Non-negotiables, restated as enforceable checks

These are requirements with tests, not vibes:

1. **Preload everything.** No dynamic generation at play time. Decks are pressed from a candidate pool ahead of the session. Test: the PWA makes zero network calls during play except telemetry flush. The press makes zero live calls (embeddings come from a locally cached model; the receipt records the model id and file hash).
2. **Our score is the hypothesis, the swipes are the observation.** `our_score` and `our_components` ride in the card JSON and are NEVER rendered. Test: grep the app source for `our_score` and `our_components`; the only permitted references are in the telemetry passthrough and a unit test asserting they never reach the DOM.
3. **Every swipe streams with persona attribution.** Offline play queues locally and flushes. Test: airplane-mode drill in the Prove section.
4. **Fun is a requirement.** Sound, motion, streaks, a jackpot mechanic. If it feels like a form it failed. Acceptance is subjective but the mechanics below are mandatory.
5. **Zero em dashes anywhere.** Add `scripts/check_no_em_dash.sh` that greps the repo for U+2014 and fails nonzero on any hit; wire it into whatever check gate the repo already runs. Run it on this file too.
6. **Deterministic press.** Same pool, same seed, same flags, byte-identical deck JSON. Test: press twice, `sha256sum` must match.
7. **Receipts on every card**: `record_id`, `source_url`, `retrieved_at`. Also a receipt file per press and per report, in the repo's existing receipt format.

---

## Landing 1: candidate pool and deck presser (`lila/deck/`)

### 1.1 `pool_build.py <client>`

Build a candidate pool from the store, deliberately wider than the report keeps:

- All tier 1 and tier 2 keeps.
- The tier 3 layer.
- Rival awards with a period-of-performance end date.
- Forecasts.
- Closed RFIs.
- eBuy rows if present for the client's category.
- A near-miss set, which is the salt: rows that superficially resemble keeps but should be left-swiped by anyone paying attention. Three flavors, tagged in a `near_miss_reason` field:
  - `vocab_hit_scope_unrelated`: vocabulary match, scope has nothing to do with the client.
  - `expired`: real fit, clock already dead.
  - `out_of_category_shared_terms`: shared terms, wrong category entirely.

Target 200 to 400 rows per client. Fail loudly below 150; note it in the receipt if between 150 and 200.

Each row gets the six-term score and its components computed at build time, stored in the row, hidden from every rendering path. Emit `lila/decks/pool_<client>_<date>.json` plus a receipt (row counts by kind, near-miss counts by reason, score model version, embedding model id and hash, store snapshot timestamp).

Matched-sentence embeddings are computed here, once, with a small local model (default `all-MiniLM-L6-v2` unless the repo already standardizes on something; check CONVENTIONS). Stored on the row as `sentence_vec`. Never computed at press or play time.

### 1.2 Card schema (JSON)

One card per pool row selected into a deck:

```json
{
  "id": "string, stable record id, doubles as the receipt record_id",
  "client": "varonis",
  "kind": "notice | rival_award | forecast | closed_rfi | rfq | near_miss",
  "seal_key": "agency seal asset key, preloaded in the app bundle",
  "agency": "string",
  "office": "string",
  "title": "string",
  "basis": "one line in the CO's words, the matched sentence, max 160 chars, hard-truncated with ellipsis at a word boundary",
  "clock": { "date": "YYYY-MM-DD", "label": "responses due | PoP ends | forecast qtr | closed" },
  "dollars": "number or null, only if published",
  "incumbent": "string or null",
  "contact_present": "bool, no PII on the card, ever",
  "source_url": "string",
  "our_score": "float, hidden, never rendered",
  "our_components": { "openness": 0.0, "clock": 0.0, "fit_tier": 0.0, "account": 0.0, "access": 0.0, "dollars": 0.0 },
  "salt": "bool, true only for near_miss",
  "overlap": "bool, true when the card is in the controlled cross-persona overlap set",
  "retrieved_at": "ISO 8601"
}
```

Use the six-component keys exactly as the docs name them; the keys above are placeholders until step zero confirms them.

### 1.3 `deck_press.py <client> --persona <slug> --n 50|100 --salt 0.33 --seed <int>`

Samples a deck from the pool:

- Stratified by kind, so a deck is not 90 percent forecasts. Strata proportions come from the pool's own kind distribution among non-salt rows, then salt is layered in at the ratio.
- Salted at `--salt` (default 0.33): that fraction of the deck is near-miss cards, interleaved, never bunched (no two salt cards adjacent when avoidable).
- Ordered by a fixed shuffle seeded from `--seed`, so pressing two personas of the same person yields controlled overlap: 30 percent of cards shared between the two decks, each shared card flagged `overlap: true` in both. Implementation: derive the overlap set from `seed` alone, derive each persona's remainder from `hash(seed, persona_slug)`, so any two personas pressed from the same seed share exactly the overlap set.
- Deterministic: `random.Random(seed)` only, no wall-clock, no dict-order dependence, stable sort keys everywhere. Two runs are byte-identical.

Emits `deck_<client>_<persona>_<date>.json` (deck id inside is `sha256` of contents, first 12 hex) and a receipt: counts by kind, salt count, overlap count, seed, pool file hash.

### 1.4 Personas: preloaded modules

`lila/personas/<slug>.json`:

```json
{
  "slug": "oem_ceo",
  "display_name": "CEO",
  "role_line": "You are the CEO of a data-security OEM. Swipe right on anything you would put a rep on this week.",
  "client": "varonis"
}
```

Ship five: `oem_ceo`, `oem_federal_vp`, `oem_ae`, `channel_rep`, `capture_lead`, each with a role line written in the second person, one sentence, a concrete action verb ("put a rep on", "call the contact", "register the deal"). Persona switch mid-session deals the next persona's pressed deck; the app never generates one.

**Definition of done, Landing 1**: `pool_build.py varonis` runs against the store and emits a pool of 200 to 400 rows with receipts; `deck_press.py` presses three persona decks with a fixed seed, byte-identical on re-run; a unit test proves the 30 percent overlap and the salt interleave; the no-em-dash check passes.

---

## Landing 2: the swipe app (`lila/app/`), a PWA

### 2.1 Shell

Single-page mobile web app. Vanilla JS, no framework (nothing in this app justifies one; if CONVENTIONS mandates a stack, use its lightest option). `manifest.webmanifest` plus a service worker for installability and offline: cache the app shell and the loaded deck; queue telemetry in IndexedDB. Loads deck JSON named by the signed URL, renders one card at a time.

### 2.2 Card face

Seal, agency, title, the CO sentence, the clock (date plus label, with a color ramp as it nears), dollars if published, incumbent tag if any, a small "contact on record" dot when `contact_present`. Nothing of ours: no lane tag, no why-now, no score, no components, no salt hint, no overlap hint. The card must read like the government wrote it.

### 2.3 Gestures

Swipe left = not relevant. Swipe right = relevant. Swipe distance is captured as intensity from gesture length at release, normalized to card width: below 0.55 is lean, at or above is strong (one constant, `INTENSITY_THRESHOLD`, in one place). No extra tap for intensity. Desktop: left and right arrows (arrows alone are lean; hold Shift for strong). The card follows the finger with rotation and a growing edge glow, green right, red left, so intensity is legible before release.

### 2.4 Reason chips

After each swipe, a one-second chip row slides in where the card was. Tap one or ignore; either way the next card deals after the window. Ignore is a valid label and is recorded as `reason: null`.

- Right chips: `fit`, `timing`, `money`, `access`.
- Left chips: `wrong category`, `too small`, `closed or dead`, `wrong buyer`, `cannot win`.

### 2.5 Super like

One available per ten cards played. Casino-styled: a pull-down gesture on the card arms it (slot-machine lever), release fires a jackpot sound and a confetti burst (tiny canvas implementation, no dependency). Meaning shown once on first use: "I would call this contact tomorrow." Stored as its own label, `super_like: true`, on top of a right swipe. Unused super likes do not accumulate past one.

### 2.6 End of persona block

Two screens:

1. **Ordering screen**: the persona's right swipes, max 8 (most recent 8 if more), as a drag-to-order list, prompt "Order these by where you would put a rep first." This is the pairwise data. Submitting posts an ordering row.
2. **Summary card**: cards played, longest streak, super likes fired, salt-free run if they caught every near miss (do not say "salt", say "no dead cards taken"), and a share tile (canvas-rendered image with the streak and deck date, native share sheet where available).

### 2.7 Fun layer

- Sound on swipe: short and distinct left vs right, synthesized with WebAudio oscillators so the repo carries no binary audio assets. Right is a rising two-note blip, left a low thunk, super like a three-note jackpot roll.
- Haptics: Vibration API where supported (Android). iOS Safari has no web haptics, so pair the sound with a 120 ms visual pulse on the card frame.
- Streak counter: consecutive swipes without an ignore-timeout, with small escalating flair at 5, 10, 20.
- A light progress ring around the deck count.
- A "deal me another persona" button on the summary card that loads the next pressed deck for this exec.
- A mute toggle, persisted, because executives play in meetings.

### 2.8 Telemetry

Per swipe, one event:

```json
{
  "event_id": "uuid, client-generated, idempotency key",
  "persona": "slug",
  "exec_id": "opaque, from the deck token",
  "deck_id": "string",
  "card_id": "string",
  "direction": "left | right",
  "intensity": "lean | strong",
  "reason": "chip slug or null",
  "super_like": false,
  "ms_on_card": 0,
  "position_in_deck": 0,
  "overlap": false,
  "device_class": "phone | tablet | desktop",
  "ts": "ISO 8601, client clock"
}
```

Events append to an IndexedDB queue immediately on swipe. A flusher batch-posts to the endpoint on: queue length 10, `online` event, `visibilitychange` to hidden, and block end. Server dedupes on `event_id`, so retries are safe. Nothing blocks the next card on network.

### 2.9 Access

Each deck link is a signed URL for one exec and one client. No accounts, no login. Token payload: `{deck_id, exec_id, persona, client, exp}`, HMAC-SHA256 signed server-side, base64url in the path: `https://<host>/d/<token>`. Persona rides in the payload, never typed. The app reads persona and exec_id from the token and stamps every event with them.

**Definition of done, Landing 2**: installable on a phone from the signed URL; plays a pressed Varonis deck end to end offline after first load; swipes, chips, super like, ordering, summary all work; sounds and pulses fire; no field of ours ever renders (asserted by test); telemetry queues offline and flushes when the radio returns.

---

## Landing 3: hosted endpoint and swipe store (`lila/api/`)

### 3.1 Service

Pick the lightest thing the repo already uses. If the repo has no service, a single Python FastAPI app on Fly.io with SQLite on a volume (Litestream or Fly volume snapshots for durability; Postgres only if the repo already runs one). Endpoints:

- `POST /swipes`: batch of 2.8 events. Auth by signed deck token in the `Authorization` header. Validates the token, checks `deck_id` matches, upserts on `event_id`.
- `GET /decks/<id>`: serves the pressed deck JSON to a valid token holder. This is the only read the app makes.
- `POST /orderings`: `{persona, exec_id, deck_id, ranked_card_ids[], ts}` from the end-of-block screen.
- `GET /healthz`.

Tables mirror the payloads: `swipes` (all 2.8 fields plus `received_at`), `orderings`, `decks` (deck JSON blob plus press receipt), `tokens` (issued, exec display name, revocable). Migrations checked in, even for SQLite.

Token minting is a CLI, `mint_link.py <deck_file> --exec-name "..."`, run at press time; it prints the full URL. Exec chooses a display name at first open; that name is the only PII anywhere and it lives in `tokens`, not on swipes.

### 3.2 Attribution

Per-persona attribution is first-class: every swipe and ordering row carries `persona` and opaque `exec_id`. Reports group by persona first, exec second, pooled third.

### 3.3 `swipe_report.py <client>`

The read after every session. Per card:

- Our rank (by `our_score` within the deck) vs swipe-derived rank, per persona and pooled. Swipe-derived rank: sort by label (super like 4, right-strong 3, right-lean 2, left-lean 1, left-strong 0), tie-break by ordering-screen position where present, then by `ms_on_card` ascending.
- Agreement rate: Kendall tau between our rank and the crowd rank, per persona and pooled, plus a plain top-10 overlap count because tau does not read well in a meeting.
- Where personas disagree with each other: cards with the widest label spread across personas, listed.
- Salt catch rate: fraction of near-miss cards left-swiped, per persona. This is the session quality gauge.
- A receipt: decks covered, event counts, execs, date range, deck hashes.

This report feeds the model band in the client artifact.

**Definition of done, Landing 3**: deployed endpoint receives, dedupes, and stores batched swipes and orderings with correct persona attribution; signed tokens gate everything; `swipe_report.py` prints the comparison table from stored rows.

---

## Landing 4: the ranker and its monitor (`lila/model/`)

### 4.1 Day-one ranker

LambdaMART via LightGBM `lambdarank`. Labels: relevance 0 to 3 from left-strong, left-lean, right-lean, right-strong; super like is 4. End-of-block orderings enter as additional pairwise constraints (materialized as duplicate rows with adjusted labels within the deck group, or via LightGBM position weighting; pick one, document it in the training receipt). Trained per persona and pooled. Query group = deck.

Features: the six components, notice kind, tier, days remaining, agency, vehicle, incumbent flag, rival flag, dollars bucket, matched-sentence embedding (`sentence_vec`, already on the row). The feature list is a checked-in allowlist. `salt` is a held-out check, never a feature; a unit test asserts it is absent from the allowlist and from the trained model's feature names.

### 4.2 Promotion gate

Until a persona has 300 labels, the ranker is not allowed to change the client artifact. Below the threshold, the artifact orders by the six-term hand score with weights fitted by logistic regression on the swipes so far (labels 0 or 1 by direction, six components as features, weights normalized and written into the artifact receipt). At or past the threshold, LambdaMART orders the artifact and the method band prints: `ranked by <persona> model, trained on N swipes from M executives, agreement rate X`.

### 4.3 The monitor (`lila/model/monitor.py`)

Run after every session and nightly. Checks:

1. Label volume per persona vs the 300 gate.
2. Salt catch rate: below 70 percent flags the session lazy or confused, and its labels are quarantined from training (kept, marked, excluded by default).
3. Inter-persona agreement, trended.
4. Drift of feature importances between consecutive trainings.
5. Calibration on a held-out fold.
6. Whether the candidate model would move any of the top five readout rows in the client artifact, listed by name if so.

Writes a one-page receipt. Blocks promotion of a new model if any check fails, and says which. Also flags cards where the model and the crowd disagree hard (largest |model score minus crowd label| within a deck); those go back into the next press as re-test cards, a new `retest: true` flag the presser honors at up to 10 percent of a deck.

### 4.4 Output contract

Ranking output writes into the pack as:

```json
{ "ranker": { "persona": "oem_ceo", "model_id": "sha or semver", "trained_on": { "swipes": 0, "execs": 0, "through": "date" }, "scores": { "<card_id>": 0.0 } } }
```

The press reads it. Zero live calls at press: the press consumes the pack file, never a service.

**Definition of done, Landing 4**: training runs end to end on the tiny prove set; the monitor refuses promotion for insufficient labels and prints exactly why; the salt-as-feature test passes; the pack contract round-trips through the press.

---

## Prove

Run in order, capture output and screenshots into `lila/prove/`:

1. Press a Varonis pool and three decks (`oem_ceo`, `oem_federal_vp`, `oem_ae`) with a fixed seed. Print counts by kind and salt. Press twice, diff the hashes to show determinism.
2. Run the app on a phone from the signed URL: swipe 20, switch persona, swipe 20, order the rights. Confirm the endpoint received every event with the right persona. Then: airplane mode on, swipe 5, airplane mode off, confirm the 5 arrive exactly once (dedupe on `event_id`).
3. Run `swipe_report.py varonis` against those 40 events and print the comparison table.
4. Train the ranker on the tiny set only to prove the pipeline runs end to end. The monitor must refuse promotion for insufficient labels and say so in its receipt.
5. Screenshots: card face, reason chips, super like jackpot, ordering screen, summary card.

## Sequence

1. Landing 1 and Landing 2 first, in parallel if two agents (the card schema in 1.2 is the contract between them; freeze it first, in a shared `lila/schema/card.json`, before splitting). These two must be playable by Friday: a pressed deck, on a phone, swiping with sound, even if telemetry only queues locally.
2. Landing 3 next: stand up the endpoint, wire the flusher, mint real links.
3. Landing 4 last and gated: ranker, monitor, promotion rules. Nothing in 4 blocks execs playing.

## Later: head-to-head

If two execs at the same client have played the same deck, show the disagreement cards between them post-block, names optional ("Someone at your company swiped left on this"). It is the mechanic most likely to get the second exec to play, which is the real acquisition problem. Requires nothing new in the data model: overlap cards plus exec_id already give the disagreement set; build it as a post-block screen fed by one new endpoint, `GET /disagreements/<deck_id>`, gated on both execs having finished.
