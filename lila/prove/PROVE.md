# Prove transcript, satellite build, 2026-08-20

Environment: fixture pool (32 authentic-shaped rows grown from the real FRTIB
row; every row marked fixture). The real store is git-ignored in
federal-sales-os and unavailable here; every pipeline stage below runs
identically against it once `pool_build.py` real mode is wired to the FSOS
filter module.

## 1. Press: three decks, fixed seeds, counts, determinism

```
pool: 32 rows (closed_rfi 2, forecast 2, near_miss 8, notice 14 incl tier-3, rfq 1, rival_award 5)
deck cec987b7d29a  varonis fed_vp      v1 calibration  n=20 salt=7 overlap=4 hands=[6,6,8]
deck e359585bf0fc  varonis oem_ae      v1 calibration  n=20 salt=7 overlap=4
deck 9b3685c5372a  varonis channel_rep v1 calibration  n=20 salt=7 overlap=4
re-press: sha256 byte-identical (diff of hashes empty)
overlap set identical across personas, flagged in both
```

## 2. Mint: per-exec display order, recomputable, fixture guard

```
exec-alpha and exec-bravo minted on deck cec987b7d29a:
  same card set: True
  different display order: True
  positions recomputable from receipt seed (tested)
minting without --dev on a fixture deck:
  REFUSED: this deck was pressed from a FIXTURE pool.
exec history note printed when variant does not match history.
```

## 3. Sessions through the live endpoint

exec-alpha played fed_vp (20 swipes, 3 hand orderings, 3 super likes incl
retroactive, 4 duels), switched persona, played oem_ae (20 more). exec-bravo
played fed_vp. First batch redelivered to simulate airplane-mode queue
recovery: 9 events redelivered, 9 deduped, stored total 90 with zero doubles.

```
persona   exec        type        count
fed_vp    exec-alpha  duel        4
fed_vp    exec-alpha  ordering    3
fed_vp    exec-alpha  super_like  3
fed_vp    exec-alpha  swipe       20
fed_vp    exec-bravo  duel        5
fed_vp    exec-bravo  ordering    3
fed_vp    exec-bravo  super_like  3
fed_vp    exec-bravo  swipe       20
oem_ae    exec-alpha  duel        3
oem_ae    exec-alpha  ordering    3
oem_ae    exec-alpha  super_like  3
oem_ae    exec-alpha  swipe       20
total 90, replays 0
disagreements endpoint: 1 split card between the two execs, served once both finished
```

## 4. swipe_report varonis (full JSON: 03_swipe_report.json)

```
deck cec987b7d29a pooled: NDCG@10 0.9576, top-10 overlap 8, pairwise accuracy 0.8846, tau 0.6947
deck e359585bf0fc pooled: NDCG@10 0.8661, top-10 overlap 8, pairwise accuracy 0.7692, tau 0.5263
salt catch: fed_vp 1.0, oem_ae 1.0 (simulated execs are attentive)
by-kind agreement printed per deck; near_miss and rival_award lower, as expected
```

## 5. Trainer and monitor

```
labels 39 (salt held out), pairs 52 (orderings + duels)
lambdarank trained: 39 rows, 3 groups, 18 allowlisted features, pair_adjustment:v1
fallback weights (ridge toward hand prior): openness .2168 clock .2133 fit_tier .2353
  account .1431 access .0953 dollars .0961   (hand: .20 .20 .25 .15 .10 .10)

MONITOR VERDICT:
  PROMOTION BLOCKED: label_volume: insufficient labels: 39 pooled, gate is 300.
  The ranker is not allowed to change the client artifact.
  (calibration also blocks: one held-out session is not a meaningful fold)
  exit code 3; receipt at lila/model/out/monitor_varonis.receipt.json
```

## 6. Tests

29 passing: schema against the real FRTIB row, recomputed days_remaining,
byte-identical press, cross-persona overlap, salt authenticity and spread,
per-exec permutation, retest-inside-overlap, token tamper and expiry, event
dedupe, server-side replay marking, attribution mismatch rejection,
disagreements endpoint, mint receipt recomputability, per-exec label
normalization, sample-aware salt gate, rapid-fire detection, metrics,
salt-never-a-feature, fallback shrinkage, monitor refusal, casino-bias check,
and the house-rules greps over the app source.

## 7. Screenshots

See lila/prove/screenshots/ (card face, reason chips, super like jackpot,
duel, hand ordering, payout).
