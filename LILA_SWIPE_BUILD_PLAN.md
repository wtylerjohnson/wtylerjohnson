# LILA SWIPE: build plan for Claude Code

A swipe deck of federal pursuits that executives play on their phones, per persona. Every judgment streams back to a hosted endpoint and trains the ranker that orders the Federal Market Map. Casino-fun on the surface, a labeling instrument underneath.

This document is the execution plan, revision 4: revision 2's store reconciliation, revision 3's casino layer, and the strategy review of 2026-08-20 folded in with Tyler's locked decisions. The goal the design now optimizes for: collect as much clean ranking data as possible per unit of executive attention, to inform LambdaMART and priority opportunity relevance surfacing. Each landing has a definition of done and a prove step. Tyler merges.

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

- `INTENSITY_DISPLAY_THRESHOLD = 0.55` (display bin only; the raw gesture is always captured, and the final relevance mapping lives in training code, never frozen in the browser)
- `OVERLAP_RATIO = 0.20` (one budget serving both persona consistency and model-disagreement retesting)
- `SALT_RATIO_FIRST_DECK = 0.33` (per-exec calibration deck)
- `SALT_RATIO = 0.15` (all later decks for that exec)
- `HAND_SIZES = [15, 15, 20]` (a 50-card deck)
- `DUELS_PER_HAND = 2` (up to 3)
- `CLIENT_LABEL_GATE = 300` (pooled across personas, per client)
- `PERSONA_LABEL_GATE = 300` (per persona, for persona-specific models)
- `EMBEDDING_VECTOR_GATE = 1000` (usable labels per client before full vectors enter the model)
- `SALT_MIN_JUDGMENTS = 8` (no salt-based quarantine below this count)
- `SALT_CATCH_NULL = 0.70` with a one-sided binomial test, `SALT_ALPHA = 0.05`
- `RAPID_FIRE_MS = 800`, `RAPID_FIRE_RUN = 5`

No client-specific overrides until evidence says otherwise.

### Personas

Four ship in v1: `fed_vp`, `oem_ae`, `channel_rep`, `capture_lead`. All play against the same Varonis pool so differences between personas are measurable. Role framing is persona-specific and aware of the client's category (data security OEM for Varonis) while the schema stays generic. **Persona attribution attaches to every interaction row, not just the session.**

---

## Non-negotiables, restated as enforceable checks

The original contract, unchanged by the strategy revisions:

1. **Preload everything.** No dynamic generation or live retrieval at play time. Decks are pressed from a candidate pool ahead of the session. Test: the PWA makes zero network calls during play except telemetry flush. The press makes zero live calls (embeddings come from a locally cached model; the receipt records the model id and file hash).
2. **Our score is the hypothesis, the swipes are the observation.** `our_score` and `our_components` ride in the card JSON and are NEVER rendered. Test: the only permitted references in app source are the telemetry passthrough and a unit test asserting they never reach the DOM.
3. **Every event streams with persona attribution.** Offline play queues locally and flushes. Test: airplane-mode drill in the Prove section.
4. **Fun is a requirement.** Sound, motion, streaks, chips, a jackpot mechanic, novelty every block. If it feels like a form it failed. Bounded by the house rules in 2.10: the chrome can gamble, the card cannot, and no mechanic may reward a swipe direction.
5. **Zero em dashes anywhere.** `scripts/check_no_em_dash.sh` greps the repo for U+2014 and fails nonzero on any hit; wire it into the repo's existing check gate. This file passes it.
6. **Deterministic and reproducible pressing.** Same pool, same seeds, same flags, byte-identical card set. Per-exec display order is also deterministic, from the seed recipe in 1.3. Test: press twice, `sha256sum` must match; recompute a display order from its receipt seeds and match positions.
7. **Receipts on every card**: `record_id`, `source_url`, `retrieved_at`. Also a receipt file per press, per mint, and per report, in the repo's existing receipt format.
8. **Signed links, no accounts.** One exec, one client, persona in the payload, key from the environment.

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

Target 200 to 400 rows per client. Fail loudly below 150; note it in the receipt between 150 and 200. Rival awards need capping in the stratification so the 508 do not dominate.

Each row gets the six components derived here (normalized to `[0, 1]`, raw inputs retained), `days_remaining` recomputed from the build date, and the matched sentence extracted. Note: the materialized rows carry `matched_term` and `all_matched_terms`, not a sentence. `pool_build.py` pulls the sentence containing the top matched term from the notice description text in `notices.db`, in the CO's words, and stores it as `basis` (max 160 chars, hard-truncated at a word boundary). Emit `lila/decks/pool_<client>_<date>.json` plus a receipt (row counts by kind, near-miss counts by reason, component derivation version, embedding model id and hash, store snapshot timestamp).

Matched-sentence embeddings are computed here, once, with a small local model (default `all-MiniLM-L6-v2` unless CONVENTIONS standardizes on something else). Stored on the row as `sentence_vec`, the full vector, always. The model consumes scalar reductions of it until the gate in 4.1; the full vector is retained for later models regardless.

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
| `overlap` | bool, set at press; the overlap budget serves persona consistency AND model-disagreement retesting, one budget, no separate duplicate-card pools |
| `retest` | bool, set at press when the card returns on model-crowd disagreement; rides inside the overlap budget |
| `retrieved_at` | copied from source row |

### 1.3 `deck_press.py <client> --persona <slug> --n 50|100 --salt <ratio> --deck-version <v>`

Presses a deterministic **card set**. Display order is per executive and applied at mint, not here.

**Seed recipe** (locked):

```text
card_set_seed = hash(client, persona, deck_version)
display_order_seed = hash(card_set_seed, opaque_subject_id, persona)
```

Never use the executive's name or email in any seed; `opaque_subject_id` is the opaque `exec_id`. The card set is identical for every exec playing that persona deck version; the display permutation differs per exec, deterministically. A replay by the same executive retains the same order unless a new deck version is minted. The mint receipt stores the order seed and the resulting card positions.

Sampling:

- Stratified by kind from the pool's own non-salt distribution, with a cap on `rival_award` share; salt layered in at the ratio, interleaved, no two salt cards adjacent when avoidable.
- **Adaptive salt is per exec**: each executive's first deck is pressed at `SALT_RATIO_FIRST_DECK` (0.33, the calibration deck); all later decks at `SALT_RATIO` (0.15). In practice: press a calibration variant and a standard variant per persona deck version; `mint_link.py` selects by the exec's play history. Salt records remain authentic near-misses, never synthetic.
- Controlled overlap at `OVERLAP_RATIO` (0.20) between any two persona decks of the same deck version: the overlap set derives from `card_set_seed` components shared across personas; each persona's remainder derives from its own `card_set_seed`. Overlap cards are also the retest channel: once a model exists, model-crowd disagreement cards fill overlap slots first, flagged `retest: true`.
- **Hands**: a 50-card deck divides into hands of 15, 15, and 20. Hand membership follows display order (positions 1 to 15, 16 to 30, 31 to 50 of the per-exec permutation), so hand boundaries are uniform even though card order is not.
- **Adaptive sampling once a usable model exists** (day one remains purely stratified): weight future decks toward predicted top-band records (surfacing errors there are the expensive ones), uncertain middle records (where LambdaMART learns), and explicit disagreement and retest records. Preserve a minimum allocation by pursuit kind so adaptive sampling does not collapse the deck into notices only; the floor per kind is a config constant.
- Deterministic: `random.Random(seed)` only, no wall-clock in sampling, stable sort keys. Byte-identical card set on re-run. `days_remaining` freshness comes from pool build date, stamped in the deck header, keeping the press itself pure.

Emits `deck_<client>_<persona>_<version>.json` (deck id is sha256 of contents, first 12 hex) and a receipt: counts by kind, salt count and ratio, overlap and retest counts, seeds, pool file hash, sampling weights used.

The deck JSON also carries a `table` block for the casino layer, pressed ahead like everything else: the dealer line set, the streak flair schedule, the between-hand bonus interval parameters, candidate duel pairs (uncertainty pairs, once a model exists), and the prior-exec count for the scarcity line. No play-time generation.

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

**Definition of done, Landing 1**: `pool_build.py varonis` runs locally against the full store and emits a 200-to-400-row pool with receipts; the schema test passes against the checked-in fixture row; `deck_press.py` presses calibration and standard variants byte-identically on re-run; unit tests prove the 0.20 overlap, the salt interleave, the seed recipe (same exec same order, different execs different orders, recomputable from receipts); the no-em-dash check passes.

---

## Landing 2: the swipe app (`lila/app/`), a PWA

### 2.1 Shell

Single-page mobile web app, vanilla JS, no framework (if CONVENTIONS mandates a stack, use its lightest option). Static, deployable on the existing Netlify setup. **The v1 requirement is instant play from a signed Safari URL**: the first swipe must be reachable with zero installs, zero prompts, zero logins. `manifest.webmanifest` plus a service worker make it installable for those who bother, and cache the shell and loaded deck for offline play; installation must never block or delay the first swipe. Telemetry queues in IndexedDB. The app applies the per-exec display permutation from `display_order_seed` delivered in the token payload, with a deterministic Fisher-Yates.

### 2.2 Card face

Seal, agency, title, the CO sentence, the clock (date plus label, color ramp as it nears), dollars if published, incumbent tag if any, a small "contact on record" dot when `contact_present`. Rival-award cards are unmistakably labeled as rival or incumbent records, never presented as the client's own awards, and always carry their public receipt. Nothing of ours renders: no lane tag, no why-now, no score, no components, no salt hint, no overlap or retest hint.

### 2.3 Gestures: capture the interpretation AND the raw gesture

Swipe left = not relevant. Swipe right = relevant. The card follows the finger with rotation and a growing edge glow, green right, red left.

Captured per swipe, all of it, always:

- signed normalized swipe distance (float, release point over card width, negative left)
- swipe duration (ms, touch start to release)
- swipe velocity (normalized width per second at release)
- `lean | strong` display bin from `INTENSITY_DISPLAY_THRESHOLD` (0.55), used for in-app feel only
- card position in hand and card position in deck

The final 0-through-3 relevance mapping is NOT frozen in the browser: intensity is normalized per executive during training (within-session standardization), where the mapping can be revised without an app release. Desktop: arrows are lean, Shift-arrow is strong, and the raw fields record the keyboard equivalents.

### 2.4 Reason chips

After each swipe, a one-second chip row slides in where the card was. Tap one or ignore; the next card deals either way. Ignore records `reason: null` and is a valid label.

- Right: `fit`, `timing`, `money`, `access`.
- Left: `wrong category`, `too small`, `closed or dead`, `wrong buyer`, `cannot win`.

### 2.5 Super like: one per hand, immediate or retroactive

One super like per hand, non-accumulating across hands. Casino-styled: pull-down on the card arms it (slot lever with resistance and a ratchet sound), release fires a jackpot roll and a canvas confetti burst (no dependency). Shown once on first use: "I would call this contact tomorrow." The lever glints on availability (a function of hand position), never on a particular card, per the house rules in 2.10.

If the lever was not pulled during the hand, the executive may promote the number-one card on that hand's ordering screen to a super like (a small lever icon on the top slot). Every super like records its mode: `immediate` or `retroactive`. Super likes are their own event type (2.8).

### 2.6 Hands, mini-orderings, duels, payout

A 50-card deck plays as three hands (15, 15, 20). After each hand, in order:

1. **Hand ordering screen**: that hand's right swipes as a drag-to-order chip stack, prompt "Order these by where you would put a rep first." Each hand's ordering persists independently the moment it is submitted, so abandonment after hand one still banks hand one's pairwise data. Retroactive super-like promotion lives on this screen. Rival-award cards keep their rival labeling.
2. **Duels**: two or three head-to-head rounds, two cards side by side, tap the winner. Direct pairwise events, the highest-information gesture per second. Pairs draw from the executive's recent right-swipes initially; once a model exists, uncertainty pairs pressed into the deck's `table` block take priority. Each duel records both record ids, the winner, persona, hand id, `sampling_reason` (`recent_rights | uncertainty_pair | disagreement`), and response time. Styled as a quick heads-up round between hands, ten seconds, skippable (a skipped duel records nothing).
3. **Between-hand payout moment**: chips bank with a slot-reel settle, streak carries over, next hand deals from the shoe.

At deck end, **the payout screen**: counters spin up like a slot payout. Cards played, longest streak, super likes fired, "no dead cards taken" if every near miss was caught (never say salt), chips banked, title progress (2.10), and the share tile. **The share tile contains no card contents**: streak, chip count, title, deck date, and branding only, because executives screenshot and forward these.

### 2.7 The casino layer

Sound, motion, and feel. All sounds synthesized with WebAudio oscillators (no binary audio assets). **Sound is on after the first user interaction** (which is also what browser autoplay policy requires), with an obvious mute control, preference persisted.

- **The deal**: cards enter from a shoe at the top of the screen with a riffle sound and a slight arc, not a fade-in. The deck is "the shoe"; the progress ring around it depletes as cards are dealt, and hand breaks read as table breaks.
- **Swipe feel**: momentum physics; release past threshold flings the card off-screen with a whoosh (pitch differs left vs right), release short snaps back with a rubber-band wobble. Right is a rising two-note blip, left a low thunk, super like a three-note jackpot roll, duels a quick card-flip snap. Chip taps click like a chip on felt.
- **Haptics**: Vibration API where supported (Android). iOS Safari has no web haptics: pair every sound with a 120 ms visual pulse on the card frame.
- **Heat**: the streak flame grows through 5, 10, 20 with escalating color and a low ember hum at 20. Streak means continuous play (no idle gap over 8 seconds), never a run of any direction. Ignoring reason chips does not break streak; walking away does. A broken streak cools with a hiss, no punishment beyond the reset.
- **Chips**: a session currency. Every swipe banks chips; the streak multiplier (x1 to x2, capped) pays identically for left and right. Chips buy nothing in v1; they are the score that makes the payout screen and share tile worth screenshotting.
- **Between-hand bonus**: the slot-reel tick and chip bonus attach to hand breaks and variable intervals from the session RNG, never to a card.
- **Table talk**: rotating one-line dealer voice, dry, text only, prewritten in the deck press ("Fresh shoe.", "The table is hot.", "Heads-up round.").
- **Scarcity and rivalry**: "You are the 2nd executive at Varonis to play this shoe" when true (count pressed into the deck JSON).
- **A "deal me another persona" button** on the payout screen, styled as moving to a new table.

### 2.8 Telemetry: four event types, one queue

Four event types: `swipe`, `ordering`, `super_like`, `duel`. **Every event of every type carries `persona`, `exec_id`, `deck_id`, `kind` (of the card, or of both cards for duels), `hand_id`, `replay`, and `ts`.** Attribution is per interaction row, never per session wrapper.

Swipe event:

```json
{
  "type": "swipe",
  "event_id": "uuid, client-generated, idempotency key",
  "persona": "slug",
  "exec_id": "opaque",
  "deck_id": "string",
  "card_id": "string",
  "kind": "notice",
  "hand_id": "deck_id:1",
  "direction": "left | right",
  "swipe_distance": -0.82,
  "swipe_ms": 240,
  "swipe_velocity": 3.4,
  "intensity_bin": "lean | strong",
  "reason": "chip slug or null",
  "ms_on_card": 0,
  "position_in_hand": 0,
  "position_in_deck": 0,
  "overlap": false,
  "retest": false,
  "replay": false,
  "device_class": "phone | tablet | desktop",
  "streak_at_swipe": 0,
  "session_minute": 0.0,
  "since_bonus_event": 0,
  "muted": false,
  "ts": "ISO 8601, client clock"
}
```

Ordering event: `{type, event_id, persona, exec_id, deck_id, hand_id, ranked_card_ids[], kinds[], replay, ts}`, one per hand, persisted independently.

Super-like event: `{type, event_id, persona, exec_id, deck_id, card_id, kind, hand_id, mode: "immediate" | "retroactive", replay, ts}`. The super-like event is the authoritative record; the swipe row does not carry the flag.

Duel event: `{type, event_id, persona, exec_id, deck_id, hand_id, card_a, card_b, kinds[], winner, sampling_reason, response_ms, replay, ts}`.

The game-state fields (`streak_at_swipe`, `session_minute`, `since_bonus_event`, `muted`) exist so the monitor can test whether the casino layer bends the labels (2.10, rule 4).

**Queue and flush**: all events append to the IndexedDB queue immediately; the queue is the source of truth when transmission fails. The flusher batch-posts on: end of each hand, queue length 10, `online` event, and `visibilitychange` to hidden. On `pagehide`, a final `sendBeacon` carries whatever remains, and beaconed events stay in the queue until the server acknowledges them on next load (dedupe by `event_id` makes the overlap safe). Nothing blocks the next card on network.

**Replay**: a second full play under the same token is stored with `replay: true` on every event, never silently mixed with first-play observations. The client flags it (it knows the deck was completed) and the server enforces it (3.1). Replays retain the same display order unless a new deck version is minted.

### 2.9 Access

Each deck link is a signed URL for one exec and one client. No accounts. Token payload `{deck_id, exec_id, persona, client, display_order_seed, exp}`, HMAC-SHA256 signed, base64url in the path: `https://<host>/d/<token>`. Persona rides in the payload, never typed. **The signing key comes from the deployment environment and is never committed.**

### 2.10 House rules: gamification never touches the label

The mechanic is the acquisition; the label is the product. One governing rule: **the chrome can gamble, the card cannot.** Enforced constraints, each with a test where feasible:

1. No mechanic may reward or celebrate a swipe **direction**. Chips, streaks, and multipliers pay identically for left and right. A right-swipe confetti would teach execs to swipe right; there is none. Only the super like celebrates, because the super like IS the label.
2. No per-card correctness feedback, ever. Salt catches are revealed only in aggregate on the payout screen ("no dead cards taken"), never on the card that was salt. Duels never reveal what the model thought.
3. No card is visually special before judgment. Bonus moments, lever glints, and dealer lines fire on counts and timers, never on the card currently shown. Retest and salt cards are pixel-identical to their kind. Test: the render path takes only card fields that appear on the face; `salt`, `overlap`, `retest`, `our_score`, and `our_components` are unreachable from it.
4. Every fun event that fires near a swipe is captured in the game-state telemetry fields (2.8) so the monitor can test whether the casino is bending the labels: right-swipe rate and intensity as a function of streak height, bonus proximity, and session minute. Drift beyond a set band flags the mechanic, not the exec.
5. Novelty budget per block: at least one element the exec has not seen before (a new dealer line set, a new streak flair tier, a new title, the head-to-head tease when it unlocks). Cheap to rotate because dealer lines and the flair schedule ride in the deck JSON, pressed ahead of time.
6. Titles: a session-spanning progression stored client-side against `exec_id` (Floor Rookie, Regular, High Roller, Whale, Pit Boss), advanced by total cards played across sessions. Titles reward volume, which is exactly what the instrument needs, and never accuracy or direction.

**Definition of done, Landing 2**: plays instantly from a signed Safari URL on a phone; offline after first load; the deal, swipe physics with raw gesture capture, hands with independent mini-orderings, duels, retroactive super likes, chips, streak flame, payout screen, sounds, and pulses all work; no field of ours ever renders (asserted by test); telemetry queues offline and flushes per hand and on `pagehide` via `sendBeacon`, with the queue as source of truth; the share tile contains no card contents.

---

## Landing 3: hosted event endpoint and store (`lila/api/`)

### 3.1 Service

A single small Python service (FastAPI) with **storage and deployment behind adapters**: a storage interface with SQLite and Postgres implementations (SQLite default), and no hard-coded host. There is no confirmed Fly or Render account; the deploy target is chosen at deploy time and supplied through environment configuration, secrets included. The static PWA stays on Netlify; only this API needs the new host.

Endpoints:

- `POST /events`: typed batch (`swipe | ordering | super_like | duel`), token in `Authorization`, validates deck match, upserts on `event_id`. **Replay detection is server-side as well as client-side**: if the token's first play is complete, subsequent full-play events are stored `replay: true` regardless of what the client sent.
- `GET /decks/<id>`: serves pressed deck JSON to a valid token holder. The only read the app makes during normal play.
- `GET /disagreements/<deck_id>`: the cross-executive disagreement mechanic, pulled forward into this landing. Once a second executive finishes the same deck, the API may issue a short disagreement deck (the cards where the two execs split, names optional: "Someone at your company swiped left on this"). This is the acquisition loop for the second exec and the third. It does not block the first Friday-playable session; it ships with this landing because it needs nothing but rows this landing already stores.
- `GET /healthz`.

Tables mirror the event payloads: `events` (typed, all fields, plus `received_at`), `decks` (deck JSON plus press receipt), `tokens` (issued, exec display name, deck version, play state for replay detection, mint receipt with order seed and positions, revocable). Migrations checked in, even for SQLite.

`mint_link.py <deck_file> --exec-name "..."` mints tokens at press time: selects calibration vs standard salt variant by the exec's play history, computes `display_order_seed` per the 1.3 recipe, writes the mint receipt (order seed, resulting positions), prints the full URL. Tyler sends it personally. The exec display name in `tokens` is the only PII anywhere; it never rides on events.

### 3.2 Attribution

Per-persona attribution is first-class on every row of every event type: `persona` plus opaque `exec_id`. Reports group by persona first, exec second, pooled third, and by `kind` throughout.

### 3.3 `swipe_report.py <client>`

The read after every session. The evaluation hierarchy, in order:

1. `NDCG@10` (primary: the product is priority surfacing, the top of the list is what matters)
2. Top-10 overlap count (the meeting read)
3. Pairwise accuracy (from hand orderings and duels)
4. Kendall tau (secondary, whole-list diagnostic only)

Per card: our rank (by `our_score` within the deck) vs swipe-derived rank, per persona and pooled. Swipe-derived rank: training-side label from normalized intensity, tie-break by hand-ordering position, then duels, then `ms_on_card` ascending.

Also in the report:

- Agreement and model quality **by kind as well as overall** (rival awards and forecasts carry different label semantics than open notices; do not read cross-kind agreement literally).
- Where personas disagree with each other: widest label spread, listed.
- Session quality: the sample-aware salt gate result (see 4.3) and rapid-fire flags, per session.
- Cross-exec disagreement summary where two execs share a deck.
- A receipt: decks covered, event counts by type, execs, date range, deck hashes.

This report feeds the model band in the client artifact.

**Definition of done, Landing 3**: deployed endpoint receives, dedupes, and stores all four event types with per-row persona attribution; replay detection works server-side; signed tokens gate everything; the signing key lives only in the environment; the disagreement endpoint issues a short deck once a second exec finishes; `swipe_report.py` prints the hierarchy in order, overall and by kind.

---

## Landing 4: the ranker and its monitor (`lila/model/`)

### 4.1 Day-one ranker, pooled first

LambdaMART via LightGBM `lambdarank`. Query group = deck.

**Labels**: relevance 0 to 3 from direction and per-executive normalized intensity (the mapping lives here, in training code, revisable without an app release); super like = 4, with `mode` retained as a feature of the label's provenance, not of the card. Hand orderings and duels enter as pairwise constraints within the deck group (the chosen materialization is documented in the training receipt). Duels are direct preference pairs and get full weight; orderings imply pairs with position-gap weighting.

**Pooling (locked)**: the first model is pooled across personas per client, with persona as a feature. Do not pool different clients into one v1 model. Persona-specific models exist only past `PERSONA_LABEL_GATE` for that persona.

**Features**: the six components, persona, notice kind, tier, days remaining (recomputed), agency, vehicle, incumbent flag, rival flag, dollars bucket, and embedding-derived scalars. Until the client reaches `EMBEDDING_VECTOR_GATE` (about 1,000 usable labels), the full `sentence_vec` does NOT enter LightGBM; instead:

- cosine similarity to the client capability-taxonomy centroid
- cosine similarity to that executive's prior right-swipe centroid, when enough history exists
- cosine similarity to the client's pooled right-swipe centroid

The full vector is stored on every row regardless, for later models. The feature list is a checked-in allowlist. `salt` is a held-out check, never a feature; a unit test asserts it is absent from the allowlist and from the trained model's feature names.

### 4.2 Promotion gates and the regularized fallback

- Below `CLIENT_LABEL_GATE` (300 pooled labels for the client), the ranker may not change the client artifact. The artifact orders by the six-term hand score with weights fitted by **regularized logistic regression, initialized from and shrunk toward the current hand-authored weights** (ridge penalty toward the hand prior). It must not relearn unconstrained weights from 40 swipes. Weights and the prior go in the artifact receipt.
- At the client gate, the pooled LambdaMART orders the artifact and the method band prints: `ranked by pooled <client> model, trained on N events from M executives, NDCG@10 X`.
- At `PERSONA_LABEL_GATE` for a given persona, a persona-specific model may order persona-specific views, method band naming the persona.
- Promotion is always monitor-gated (4.3).

### 4.3 The monitor (`lila/model/monitor.py`)

Run after every session and nightly. Checks:

1. Label volume: pooled per client vs `CLIENT_LABEL_GATE`, per persona vs `PERSONA_LABEL_GATE`.
2. **Sample-aware salt gate** (replaces the raw 70 percent floor): no salt-based quarantine until at least `SALT_MIN_JUDGMENTS` (8) salt judgments exist for the session; then a one-sided binomial test against `SALT_CATCH_NULL` (0.70) at `SALT_ALPHA` (0.05). Quarantine retains the events, marks them, and excludes them from training pending review.
3. **Rapid-fire signal**: runs of `RAPID_FIRE_RUN` (5) or more swipes under `RAPID_FIRE_MS` (800 ms) flag the run for review alongside the salt gate.
4. Inter-persona agreement, trended, and agreement by kind.
5. Feature-importance drift between consecutive trainings.
6. Calibration on a held-out fold; evaluation reported in the 3.3 hierarchy (NDCG@10 first).
7. Whether the candidate model would move any of the top five readout rows, listed by name if so.
8. Casino-bias check, using the game-state telemetry fields: right-swipe rate and mean intensity as a function of streak height, bonus proximity, and session minute. If mechanics measurably push direction or intensity, the receipt names the mechanic and the session, and those labels are down-weighted, not the exec blamed.

Writes a one-page receipt. Blocks promotion if any check fails, and says which. Flags cards where model and crowd disagree hard; those return in the next press inside the overlap-retest budget (1.3), and as duel `sampling_reason: disagreement` pairs.

### 4.4 Output contract

```json
{ "ranker": { "scope": "pooled | persona", "persona": "fed_vp or null", "client": "varonis", "model_id": "sha or semver", "trained_on": { "events": 0, "execs": 0, "through": "date" }, "scores": { "<card_id>": 0.0 } } }
```

Written into the pack; the press reads it. Zero live calls at press.

**Definition of done, Landing 4**: training runs end to end on the tiny prove set with orderings and duels entering as pairs; the monitor refuses promotion for insufficient labels and says so; the salt-as-feature test passes; the regularized fallback reproduces hand-weight ordering at zero labels; the pack contract round-trips through the press.

---

## Prove

Run in order, capture output and screenshots into `lila/prove/`. **The first acceptance test is a signed Varonis link played on a phone, including persona switching, three completed hands, ordering and duel receipts, offline queue recovery, and a verified endpoint flush.**

1. Press a Varonis pool (local, full store) and three decks (`fed_vp`, `oem_ae`, `channel_rep`) at a fixed deck version, calibration and standard salt variants. Print counts by kind and salt. Press twice, diff the hashes. Mint two links for the same deck to two different opaque exec ids and show the display orders differ and are recomputable from the mint receipts.
2. On a phone from the signed URL: play three full hands with mini-orderings and duels, switch persona, play a hand. Confirm the endpoint received every event type with the right persona and `kind` on each row. Then: airplane mode on, swipe 5 and complete a hand ordering, airplane mode off, confirm everything arrives exactly once. Kill the tab mid-hand and confirm `sendBeacon` plus queue recovery lost nothing.
3. Replay the same token and confirm every second-play event stored `replay: true`.
4. Run `swipe_report.py varonis` against the collected events and print the hierarchy (NDCG@10, top-10 overlap, pairwise accuracy, tau), overall and by kind.
5. Train the ranker on the tiny set only to prove the pipeline, orderings and duels included. The monitor must refuse promotion for insufficient labels and say so in its receipt, and must show the salt gate correctly declining to quarantine below 8 salt judgments.
6. Screenshots: card face, reason chips, super like jackpot (immediate and retroactive), duel screen, streak flame with chip multiplier, hand ordering as chip stack, payout screen, share tile.
7. House-rules spot check: play 10 cards and confirm chips and streak pay identically for left and right swipes, and that no salt or retest card looked different from its kind before judgment.

## Sequence (revised landing order)

1. **Freeze the schemas first**: `lila/schema/card.json` and the four telemetry event schemas, including hands, raw gesture fields, permutation receipts, replay semantics, and pairwise (ordering and duel) events. This is the contract that lets two agents split.
2. **Landing 1**: the authentic candidate pool and the deterministic card-set presser with per-exec display permutation at mint.
3. **Landing 2**: the PWA with per-exec ordering, hand breaks, mini-ordering, retroactive super likes, duels, and offline queueing. Landing 2 starts against a deterministic hand-pressed fixture deck so the app is swipeable before the pool builder finishes; 1 and 2 run in parallel after the schema freeze. Playable by Friday.
4. **Landing 3**: the hosted event endpoint, token minting, replay detection, quality gates at ingest, and cross-executive disagreement decks.
5. **Landing 4**: pooled-first evaluation, the regularized fallback, and monitor-gated LambdaMART promotion.

**Do not let modeling expansion delay the playable instrument.** Nothing in Landings 4 blocks execs playing; nothing in the adaptive-sampling machinery blocks day-one stratified pressing.

6. **Before the first real signed link goes out**: refresh the notice store (the materialization is from August 18) and repress.

## Later: head-to-head, beyond the disagreement deck

The disagreement endpoint ships in Landing 3. The fuller head-to-head experience (post-block disagreement reveal styled as a table showdown, names optional) builds on it once two execs at the same client have played the same deck. It is the mechanic most likely to get the second exec to play, which is the real acquisition problem, and acquisition is the binding constraint on total labels.

## Open items to flag in the first PR

- `FSOS_VISION_SPINE.md` and `FSOS_VARONIS_ROWS_MPT.md` are missing from the checkout: attach or restore; contents were not invented here.
- No confirmed API host or signing-key owner: choose at deploy time, keep behind the adapters, supply secrets via environment.
