# LILA SWIPE: build plan for Claude Code

A swipe deck of federal pursuits that executives play on their phones, per persona. Every judgment streams back to a hosted endpoint and trains the ranker that orders the Federal Market Map. Casino-fun on the surface, a labeling instrument underneath.

This document is the execution plan, revision 2, reconciled against Tyler's answers of 2026-08-20. It is written to be landed by Claude Code in ordered, verifiable steps. Each landing has a definition of done and a prove step. Tyler merges.

**Where this runs**: inside `federal-sales-os` (authoritative local checkout: `/Users/wtjohnson/federal-sales-os`; select the repository named `federal-sales-os` in Cursor, the clone points to a local mirror, do not assume a GitHub URL). `lila/` belongs at the root of that repo. Branch `fable/lila-swipe` from `fable/slug-consolidation`, which already contains the `fable/lila-retrieval` work and the canonical client-slug fix. This plan file and the fixture beside it (`lila_fixtures/varonis_candidate_row.json`) are authored in a satellite repo and should be carried over as the product brief and the schema test fixture.

---

## Reconciled ground truth

Facts confirmed 2026-08-20. Do not re-derive these; do not contradict them.

### Documents

- `CLAUDE.md` and `docs/CONVENTIONS.md` exist in the FSOS checkout. Where this plan and CONVENTIONS disagree, CONVENTIONS wins.
- `FSOS_VISION_SPINE.md` and `FSOS_VARONIS_ROWS_MPT.md` are NOT currently present in the checkout. **Do not invent their contents.** Use this plan as the immediate product brief and flag those two documents for attachment or restoration in the first PR description.

### The store (not one file)

- Raw SAM notice store: SQLite at `data/state/notice_store/notices.db`, about 1.5 GB, 360,384 notice rows.
- Varonis pursuit materialization: `data/state/varonis_rows_2026-08-18.json` with 181 qualifying notices, 61 tier-3 widened candidates, 508 rival awards, 6 forecasts, 12 ESI rows, and 26 Varonis period-of-performance rows.
- Client frame: `clients/varonis/profile.json`, `capability_taxonomy.json`, `engagement_scope.json`, `frame_tiers.json`.
- **Both the database and the materialized JSON live under git-ignored `data/state/` paths.** A Cloud Agent does not receive them by switching repositories. Landing 1 runs locally against the full store, or against a small checked-in fixture. The real candidate row in `lila_fixtures/varonis_candidate_row.json` is the schema test fixture.
- Any `days_remaining` in a stored row is snapshot-relative and MUST be recomputed at press time from the press date.

### The six components

The six terms (openness, clock, fit tier, account, access, dollars) are a scoring sketch, not a stored vector. Existing records carry raw ingredients: `status`, response and period-of-performance dates, `tier`, `leverage_rank`, agency identity, set-aside and vehicle information, POCs, and dollar fields where available. `pool_build.py` derives the six components, normalizes each to `[0, 1]`, and retains the raw inputs used to calculate them on the row. **Do not silently rename existing source keys.** The derivations are frozen in `lila/schema/card.json` and tested against the fixture row.

### Near-misses

Authentic store records only, never synthesized. Reference point: the August 18 Varonis run had 3,208 prefilter hits, kept 181, identified 72 tier-3-only rejects, dropped 84 family duplicates, and separately retained 61 tier-3 widened candidates. Build the near-miss pool by rerunning the filters over the raw SQLite rows and recording `selection_reason` or `rejection_reason` on every pool row. Existing press code does not need to store fictional rejects.

### Hosting and delivery

- Existing hosting is Netlify for client HTML reports, including a Varonis deployment. There is NO confirmed Fly or Render account, no Lila custom domain, no hosted transactional store, no signing-key owner. Do not assume those credentials.
- Keep hosting and persistence behind adapters (a storage interface with SQLite and Postgres implementations; a deploy target that is not hard-coded). Secrets come from the deployment environment. **Never commit a signing key.**
- The PWA is static and can ride the existing Netlify setup. The API needs a small host chosen at deploy time; the code must not care which.
- Link delivery is personal for v1: Tyler texts or messages the signed URL. `mint_link.py` printing the URL is sufficient. Email, CRM, and messaging automation are out of scope.

### Client scope

Varonis is the launch client and control deck, not a permanent limit. Everything is client-agnostic: client identity flows from the slug argument and the `clients/<slug>/` frame, never from hard-coded strings. The available Varonis materialization was retrieved August 18; refresh the notice store and repress before the first real executive session.

### Constants

Global for v1, all in one configuration module, `lila/config.py`:

- `INTENSITY_THRESHOLD = 0.55`
- `OVERLAP_RATIO = 0.30`
- `SALT_RATIO = 0.33`
- `PROMOTION_LABEL_GATE = 300`
- `SALT_CATCH_FLOOR = 0.70`

No client-specific overrides until evidence says otherwise.

### Personas

Four ship in v1: `fed_vp`, `oem_ae`, `channel_rep`, `capture_lead`. All play against the same Varonis pool so differences between personas are measurable. Role framing is persona-specific and aware of the client's category (data security OEM for Varonis) while the schema stays generic. **Persona attribution attaches to every interaction row, not just the session.**

---

## Non-negotiables, restated as enforceable checks

1. **Preload everything.** No dynamic generation at play time. Decks are pressed from a candidate pool ahead of the session. Test: the PWA makes zero network calls during play except telemetry flush. The press makes zero live calls (embeddings come from a locally cached model; the receipt records the model id and file hash).
2. **Our score is the hypothesis, the swipes are the observation.** `our_score` and `our_components` ride in the card JSON and are NEVER rendered. Test: the only permitted references in app source are the telemetry passthrough and a unit test asserting they never reach the DOM.
3. **Every swipe streams with persona attribution.** Offline play queues locally and flushes. Test: airplane-mode drill in the Prove section.
4. **Fun is a requirement.** Sound, motion, streaks, a jackpot mechanic. If it feels like a form it failed.
5. **Zero em dashes anywhere.** `scripts/check_no_em_dash.sh` greps the repo for U+2014 and fails nonzero on any hit; wire it into the repo's existing check gate. This file passes it.
6. **Deterministic press.** Same pool, same seed, same flags, byte-identical deck JSON. Test: press twice, `sha256sum` must match.
7. **Receipts on every card**: `record_id`, `source_url`, `retrieved_at`. Also a receipt file per press and per report, in the repo's existing receipt format.

---

## Landing 1: candidate pool and deck presser (`lila/deck/`)

### 1.1 `pool_build.py <client>`

Build a candidate pool from the store, deliberately wider than the report keeps:

- All tier 1 and tier 2 keeps (the 181 for Varonis as of Aug 18).
- The tier-3 widened layer (the 61).
- Rival awards with a period-of-performance end date (from the 508).
- Forecasts (the 6).
- Closed RFIs.
- ESI and eBuy rows where present (the 12 ESI rows).
- The near-miss salt set: authentic rejects from rerunning the filters over `notices.db`, tagged with a `near_miss_reason`:
  - `vocab_hit_scope_unrelated`: vocabulary match, scope has nothing to do with the client.
  - `expired`: real fit, clock already dead.
  - `out_of_category_shared_terms`: shared terms, wrong category entirely.

  Every pool row, salt or not, records its `selection_reason` or `rejection_reason` from the filter rerun.

Target 200 to 400 rows per client. Fail loudly below 150; note it in the receipt between 150 and 200. The Varonis inputs above make the target comfortably reachable; rival awards will need capping in the stratification so they do not dominate.

Each row gets the six components derived here (normalized to `[0, 1]`, raw inputs retained), `days_remaining` recomputed from the build date, and the matched sentence extracted. Note: the materialized rows carry `matched_term` and `all_matched_terms`, not a sentence. `pool_build.py` pulls the sentence containing the top matched term from the notice description text in `notices.db`, in the CO's words, and stores it as `basis` (max 160 chars, hard-truncated at a word boundary). Emit `lila/decks/pool_<client>_<date>.json` plus a receipt (row counts by kind, near-miss counts by reason, component derivation version, embedding model id and hash, store snapshot timestamp).

Matched-sentence embeddings are computed here, once, with a small local model (default `all-MiniLM-L6-v2` unless CONVENTIONS standardizes on something else). Stored on the row as `sentence_vec`. Never computed at press or play time.

### 1.2 Card schema (`lila/schema/card.json`)

Frozen first; it is the contract between Landing 1 and Landing 2 and is tested against `lila_fixtures/varonis_candidate_row.json`. Source keys are preserved, not renamed; card fields are derived and the mapping is explicit:

| card field | derivation from source row |
|---|---|
| `id` | `notice_id` (or award / forecast record id), doubles as receipt `record_id` |
| `client` | slug argument |
| `kind` | `notice \| rival_award \| forecast \| closed_rfi \| rfq \| near_miss`; from `notice_type` and `status` (e.g. Sources Sought + open maps to `notice`; Sources Sought + closed maps to `closed_rfi`) |
| `seal_key` | derived from `agency`, preloaded asset key |
| `agency`, `office`, `title` | copied as-is |
| `basis` | sentence containing top `matched_term`, extracted from notice text in `notices.db`, max 160 chars |
| `clock` | `{date, label}`; date from `response_due` or PoP end or forecast quarter; label from kind; `days_remaining` recomputed at press |
| `dollars` | published dollar fields only, else null |
| `incumbent` | incumbent or awardee name where known, else null |
| `contact_present` | bool from POC presence; no PII on the card, ever |
| `source_url` | `sam_url` or equivalent public receipt URL |
| `our_score`, `our_components` | derived six terms, hidden, never rendered |
| `raw_inputs` | the source values used in derivation (`status`, `tier`, `leverage_rank`, dates, set-aside, vehicle, dollar fields), preserved under their original key names |
| `salt` | bool, true only for `near_miss`, with `near_miss_reason` |
| `overlap` | bool, set at press |
| `retrieved_at` | copied from source row |

### 1.3 `deck_press.py <client> --persona <slug> --n 50|100 --salt 0.33 --seed <int>`

Samples a deck from the pool:

- Stratified by kind from the pool's own non-salt distribution, with a cap on `rival_award` share so the 508 do not swamp the deck; salt layered in at `SALT_RATIO`, interleaved, no two salt cards adjacent when avoidable.
- Controlled overlap: 30 percent of cards shared between any two persona decks pressed from the same seed, each flagged `overlap: true` in both. Implementation: the overlap set derives from `seed` alone; each persona's remainder derives from `hash(seed, persona_slug)`.
- Deterministic: `random.Random(seed)` only, no wall-clock in sampling, stable sort keys. Byte-identical on re-run. (`days_remaining` freshness comes from pool build date, which is stamped in the deck header, keeping the press itself pure.)

Emits `deck_<client>_<persona>_<date>.json` (deck id is sha256 of contents, first 12 hex) and a receipt: counts by kind, salt count, overlap count, seed, pool file hash.

### 1.4 Personas: preloaded modules

`lila/personas/<slug>.json`:

```json
{
  "slug": "fed_vp",
  "display_name": "Federal VP",
  "role_line": "You run federal sales for a data-security OEM. Swipe right on anything you would put a rep on this week.",
  "client": "varonis"
}
```

Ship four: `fed_vp`, `oem_ae`, `channel_rep`, `capture_lead`. Role lines are second person, one sentence, persona-specific, category-aware, with a concrete action verb ("put a rep on", "call the contact", "register the deal", "open a capture file"). Persona switch mid-session deals the next persona's pressed deck; the app never generates one.

**Definition of done, Landing 1**: `pool_build.py varonis` runs locally against the full store and emits a 200-to-400-row pool with receipts; the schema test passes against the checked-in fixture row; `deck_press.py` presses persona decks byte-identically on re-run; unit tests prove the 30 percent overlap and salt interleave; the no-em-dash check passes.

---

## Landing 2: the swipe app (`lila/app/`), a PWA

### 2.1 Shell

Single-page mobile web app, vanilla JS, no framework (if CONVENTIONS mandates a stack, use its lightest option). Static, deployable on the existing Netlify setup. **The v1 requirement is instant play from a signed Safari URL**: the first swipe must be reachable with zero installs, zero prompts, zero logins. `manifest.webmanifest` plus a service worker make it installable for those who bother, and cache the shell and loaded deck for offline play; installation must never block or delay the first swipe. Telemetry queues in IndexedDB.

### 2.2 Card face

Seal, agency, title, the CO sentence, the clock (date plus label, color ramp as it nears), dollars if published, incumbent tag if any, a small "contact on record" dot when `contact_present`. Rival-award cards are unmistakably labeled as rival or incumbent records, never presented as the client's own awards, and always carry their public receipt. Nothing of ours renders: no lane tag, no why-now, no score, no components, no salt hint, no overlap hint.

### 2.3 Gestures

Swipe left = not relevant. Swipe right = relevant. Swipe distance at release, normalized to card width, is intensity: below `INTENSITY_THRESHOLD` is lean, at or above is strong. No extra tap. Desktop: arrows are lean, Shift-arrow is strong. The card follows the finger with rotation and a growing edge glow, green right, red left, so intensity is legible before release.

### 2.4 Reason chips

After each swipe, a one-second chip row slides in where the card was. Tap one or ignore; the next card deals either way. Ignore records `reason: null` and is a valid label.

- Right: `fit`, `timing`, `money`, `access`.
- Left: `wrong category`, `too small`, `closed or dead`, `wrong buyer`, `cannot win`.

### 2.5 Super like

One available per ten cards played, non-accumulating. Casino-styled: pull-down on the card arms it (slot lever), release fires a jackpot sound and a canvas confetti burst (no dependency). Shown once on first use: "I would call this contact tomorrow." Stored as its own label on top of a right swipe.

### 2.6 End of persona block

1. **Ordering screen**: the persona's right swipes, max 8 (most recent 8 if more), drag-to-order, prompt "Order these by where you would put a rep first." This is the pairwise data. Rival-award cards may appear here with their rival labeling intact. Submit posts an ordering row.
2. **Summary card**: cards played, longest streak, super likes fired, "no dead cards taken" if every near miss was caught (never say salt), and a share tile. **The share tile contains no card contents**: streak, count, deck date, and branding only, because executives screenshot and forward these.

### 2.7 Fun layer

- Sound on swipe, synthesized with WebAudio oscillators (no binary audio assets): rising two-note blip right, low thunk left, three-note jackpot roll for super like. **Sound is on after the first user interaction** (which is also what browser autoplay policy requires), with an obvious mute control, preference persisted.
- Haptics via Vibration API where supported (Android). iOS Safari has no web haptics: pair the sound with a 120 ms visual pulse on the card frame.
- Streak counter with escalating flair at 5, 10, 20; a light progress ring; a "deal me another persona" button on the summary.

### 2.8 Telemetry

Per swipe, one event. **Persona and exec attribution ride on every event row**, not on a session wrapper:

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

Events append to the IndexedDB queue on swipe. The flusher batch-posts on: queue length 10, `online` event, `visibilitychange` to hidden, block end. Server dedupes on `event_id`; retries are safe; nothing blocks the next card on network.

### 2.9 Access

Each deck link is a signed URL for one exec and one client. No accounts. Token payload `{deck_id, exec_id, persona, client, exp}`, HMAC-SHA256 signed, base64url in the path: `https://<host>/d/<token>`. Persona rides in the payload, never typed. **The signing key comes from the deployment environment and is never committed.**

**Definition of done, Landing 2**: plays instantly from a signed Safari URL on a phone; offline after first load; swipes, chips, super like, ordering, summary, sounds, pulses all work; no field of ours ever renders (asserted by test); telemetry queues offline and flushes on reconnect; the share tile contains no card contents.

---

## Landing 3: hosted endpoint and swipe store (`lila/api/`)

### 3.1 Service

A single small Python service (FastAPI) with **storage and deployment behind adapters**: a storage interface with SQLite and Postgres implementations (SQLite default), and no hard-coded host. There is no confirmed Fly or Render account; the deploy target is chosen at deploy time and supplied through environment configuration, secrets included. The static PWA stays on Netlify; only this API needs the new host.

Endpoints:

- `POST /swipes`: batch of 2.8 events, token in `Authorization`, validates deck match, upserts on `event_id`.
- `GET /decks/<id>`: serves pressed deck JSON to a valid token holder. The only read the app makes.
- `POST /orderings`: `{persona, exec_id, deck_id, ranked_card_ids[], ts}`.
- `GET /healthz`.

Tables mirror the payloads: `swipes` (plus `received_at`), `orderings`, `decks` (deck JSON plus press receipt), `tokens` (issued, exec display name, revocable). Migrations checked in, even for SQLite.

`mint_link.py <deck_file> --exec-name "..."` mints tokens at press time and prints the full URL; Tyler sends it personally. That printed URL is the whole delivery system for v1. The exec display name in `tokens` is the only PII anywhere; it never rides on swipes.

### 3.2 Attribution

Per-persona attribution is first-class on every row: `persona` plus opaque `exec_id` on swipes and orderings alike. Reports group by persona first, exec second, pooled third.

### 3.3 `swipe_report.py <client>`

The read after every session. Per card:

- Our rank (by `our_score` within the deck) vs swipe-derived rank, per persona and pooled. Swipe-derived rank: label order (super like 4, right-strong 3, right-lean 2, left-lean 1, left-strong 0), tie-break by ordering-screen position, then `ms_on_card` ascending.
- Agreement rate: Kendall tau per persona and pooled, plus a plain top-10 overlap count for the meeting read.
- Where personas disagree with each other: widest label spread across personas, listed.
- Salt catch rate per persona: the session quality gauge.
- A receipt: decks covered, event counts, execs, date range, deck hashes.

This report feeds the model band in the client artifact.

**Definition of done, Landing 3**: deployed endpoint receives, dedupes, and stores batched swipes and orderings with per-row persona attribution; signed tokens gate everything; the signing key lives only in the environment; `swipe_report.py` prints the comparison table from stored rows.

---

## Landing 4: the ranker and its monitor (`lila/model/`)

### 4.1 Day-one ranker

LambdaMART via LightGBM `lambdarank`. Labels 0 to 4 as above. End-of-block orderings enter as additional pairwise constraints (materialized within the deck group; the chosen mechanism is documented in the training receipt). Trained per persona and pooled. Query group = deck.

Features: the six components, notice kind, tier, days remaining (recomputed), agency, vehicle, incumbent flag, rival flag, dollars bucket, `sentence_vec`. The feature list is a checked-in allowlist. `salt` is a held-out check, never a feature; a unit test asserts it is absent from the allowlist and from the trained model's feature names.

### 4.2 Promotion gate

Until a persona has `PROMOTION_LABEL_GATE` (300) labels, the ranker may not change the client artifact. Below the gate, the artifact orders by the six-term hand score with weights fitted by logistic regression on the swipes so far, weights written into the artifact receipt. At the gate, LambdaMART orders the artifact and the method band prints: `ranked by <persona> model, trained on N swipes from M executives, agreement rate X`.

### 4.3 The monitor (`lila/model/monitor.py`)

Run after every session and nightly. Checks:

1. Label volume per persona vs the gate.
2. Salt catch rate below `SALT_CATCH_FLOOR` (70 percent) flags the session lazy or confused; its labels are quarantined (kept, marked, excluded from training by default).
3. Inter-persona agreement, trended.
4. Feature-importance drift between consecutive trainings.
5. Calibration on a held-out fold.
6. Whether the candidate model would move any of the top five readout rows, listed by name if so.

Writes a one-page receipt. Blocks promotion if any check fails, and says which. Flags cards where model and crowd disagree hard; those return in the next press as `retest: true` cards, up to 10 percent of a deck.

### 4.4 Output contract

```json
{ "ranker": { "persona": "fed_vp", "model_id": "sha or semver", "trained_on": { "swipes": 0, "execs": 0, "through": "date" }, "scores": { "<card_id>": 0.0 } } }
```

Written into the pack; the press reads it. Zero live calls at press.

**Definition of done, Landing 4**: training runs end to end on the tiny prove set; the monitor refuses promotion for insufficient labels and prints exactly why; the salt-as-feature test passes; the pack contract round-trips through the press.

---

## Prove

Run in order, capture output and screenshots into `lila/prove/`:

1. Press a Varonis pool (local, full store) and three decks (`fed_vp`, `oem_ae`, `channel_rep`) with a fixed seed. Print counts by kind and salt. Press twice, diff the hashes to show determinism.
2. Run the app on a phone from the signed URL: swipe 20, switch persona, swipe 20, order the rights. Confirm the endpoint received every event with the right persona on the row. Then: airplane mode on, swipe 5, airplane mode off, confirm the 5 arrive exactly once.
3. Run `swipe_report.py varonis` against those 40 events and print the comparison table.
4. Train the ranker on the tiny set only to prove the pipeline. The monitor must refuse promotion for insufficient labels and say so in its receipt.
5. Screenshots: card face, reason chips, super like jackpot, ordering screen, summary card.

## Sequence

1. **Schema freeze first**: `lila/schema/card.json` from the real fixture row, with the source-key mapping table above, plus the schema test. This is the contract that lets two agents split.
2. **Landing 1 and Landing 2 in parallel.** Landing 2 starts against a deterministic hand-pressed fixture deck (built from the fixture row and a handful of siblings) so the app is swipeable before the pool builder finishes. These two must be playable by Friday: a pressed deck, on a phone, swiping with sound, telemetry queuing locally.
3. **Landing 3 next**: endpoint, flusher wiring, `mint_link.py`.
4. **Landing 4 last and gated**: ranker, monitor, promotion rules. Nothing in 4 blocks execs playing.
5. **Before the first real signed link goes out**: refresh the notice store (the materialization is from August 18) and repress.

## Later: head-to-head

If two execs at the same client have played the same deck, show the disagreement cards between them post-block, names optional ("Someone at your company swiped left on this"). It is the mechanic most likely to get the second exec to play, which is the real acquisition problem. Requires nothing new in the data model: overlap cards plus exec_id already give the disagreement set; one new endpoint, `GET /disagreements/<deck_id>`, gated on both execs having finished.

## Open items to flag in the first PR

- `FSOS_VISION_SPINE.md` and `FSOS_VARONIS_ROWS_MPT.md` are missing from the checkout: attach or restore; contents were not invented here.
- No confirmed API host or signing-key owner: choose at deploy time, keep behind the adapters, supply secrets via environment.
