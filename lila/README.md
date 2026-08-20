# LILA SWIPE

A swipe deck of federal pursuits that executives play on their phones, per
persona. Every judgment streams to a hosted endpoint and trains the ranker
that orders the Federal Market Map. Casino-fun on the surface, a labeling
instrument underneath. Product brief: `../LILA_SWIPE_BUILD_PLAN.md` (rev 4).

## Layout

```
lila/
  config.py            global v1 constants, one module
  schema/              frozen contracts: card.json, events.json
  personas/            fed_vp, oem_ae, channel_rep, capture_lead
  deck/                pool_build.py, deck_press.py, common.py (seeds, order, components)
  app/                 the PWA: vanilla JS, no framework, offline-first
  api/                 FastAPI service, storage adapter, tokens, mint_link.py, swipe_report.py
  model/               labels.py, features.py, train.py, monitor.py
  fixtures/            dev fixture rows (marked; never minted to real execs)
  tests/               29 tests incl house-rules greps
  prove/               PROVE.md transcript, screenshots, simulator
```

## Quick start (dev, fixture pool)

```bash
pip install -r requirements.txt
python3 lila/fixtures/make_fixture_pool.py
python3 lila/deck/pool_build.py varonis --fixture --build-date 2026-08-20
python3 lila/deck/deck_press.py varonis --persona fed_vp --n 20 --salt 0.33 --deck-version v1

export LILA_SIGNING_KEY=dev-only LILA_DB=/tmp/lila.db
python3 -m uvicorn lila.api.main:app --port 8000 &
(cd lila/app && python3 -m http.server 8080) &
python3 lila/api/mint_link.py lila/decks/deck_varonis_fed_vp_v1_calibration.json \
  --dev --app-base http://localhost:8080 --api-base http://localhost:8000
# open the printed link on a phone or browser

python3 lila/api/swipe_report.py varonis
python3 lila/model/monitor.py varonis   # exits 3 and says why until 300 labels
python3 -m pytest lila/tests -q
bash scripts/check_no_em_dash.sh
```

## Transplanting into federal-sales-os

1. Copy `lila/`, `lila_fixtures/`, `scripts/check_no_em_dash.sh`, and the plan
   onto `fable/lila-swipe` branched from `fable/slug-consolidation`.
2. Wire `lila/deck/pool_build.py::load_real_rows` to the FSOS filter module so
   near-misses are harvested from `data/state/notice_store/notices.db` reruns
   with `rejection_reason`, and the basis sentence is extracted from notice
   description text (the fixture path already exercises the identical row
   contract; the schema test pins it).
3. Reconcile the six component keys against the FSOS docs sketch and adjust
   `common.derive_components` if the canonical names differ. Raw inputs are
   retained on every row, so re-derivation is cheap.
4. Switch the press embedding provider to the locally cached sentence model
   (`--embed-provider minilm`) and record its hash in the pool receipt.
5. Deploy: PWA to the existing Netlify; API anywhere with a volume
   (`LILA_DB`, `LILA_SIGNING_KEY` from the environment; never commit a key).
6. Refresh the notice store and repress before the first real signed link.
   `mint_link.py` refuses fixture decks without `--dev` by design.

## Non-negotiables carried in code

Preloaded decks only (zero play-time generation); hidden score never rendered
(greps in tests); per-interaction persona attribution; offline queue as source
of truth with per-hand flush and pagehide beacon; deterministic press (byte
identical) with per-exec display order recomputable from mint receipts;
receipts on every card and artifact; salt never a feature; promotion gated by
the monitor; zero em dashes (checked).
