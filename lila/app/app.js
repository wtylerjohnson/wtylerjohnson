// LILA SWIPE. Casino on the surface, labeling instrument underneath.
// House rule enforced here: this file NEVER references the hidden system
// fields (score, components, salt). The aggregate salt reveal on the payout
// screen and the salt-spread in display ordering live in order.js, outside
// every render path. Tests grep this file to keep it that way.

import { displayOrder, cleanRun } from './order.js';
import { sounds, pulse, isMuted, setMuted } from './audio.js';
import { makeFlusher } from './queue.js';

const $ = id => document.getElementById(id);

// ---------------------------------------------------------------- boot
const frag = new URLSearchParams(location.hash.slice(1));
const TOKEN = frag.get('t');
const NEXT_TOKEN = frag.get('next');
const API = frag.get('api') || location.origin;

if (!TOKEN) {
  document.body.innerHTML = '<p style="padding:40px;text-align:center">This table needs an invitation. Ask for your signed link.</p>';
  throw new Error('no token');
}

function tokenPayload(tok) {
  const body = tok.split('.')[0].replace(/-/g, '+').replace(/_/g, '/');
  return JSON.parse(atob(body));
}
const PAYLOAD = tokenPayload(TOKEN);
const { deck_id, exec_id, persona, display_order_seed } = PAYLOAD;

const flusher = makeFlusher(API, TOKEN, s => {
  if (s.offline) toast(`offline: ${s.queued} judgments in the vault`);
});

// mulberry32 for game-feel randomness (bonus intervals, confetti). Seeded from
// the display order seed so a session replays identically.
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(parseInt(display_order_seed.slice(0, 8), 16));
const randInt = (a, b) => a + Math.floor(rng() * (b - a + 1));

// ---------------------------------------------------------------- state
const S = {
  deck: null,
  cards: [],           // display-ordered
  hands: [],           // [{start, size}]
  idx: 0,
  hand: 0,
  rightsThisHand: [],
  decisions: new Map(), // card_id -> direction
  superLikeUsedThisHand: false,
  superLikesFired: 0,
  streak: 0,
  bestStreak: 0,
  chips: 0,
  lastSwipeAt: 0,
  nextBonusIn: randInt(10, 14),
  sinceBonus: 0,
  swipesTotal: 0,
  sessionStart: Date.now(),
  cardShownAt: 0,
  replay: false,
  dealerIdx: 0,
};

const TITLES = [[0, 'Floor Rookie'], [50, 'Regular'], [150, 'High Roller'], [400, 'Whale'], [1000, 'Pit Boss']];
function title(total) {
  let t = TITLES[0][1];
  for (const [n, name] of TITLES) if (total >= n) t = name;
  return t;
}
const totalKey = `lila_total_${exec_id}`;
const totalPlayed = () => parseInt(localStorage.getItem(totalKey) || '0', 10);

function deviceClass() {
  const w = Math.min(window.innerWidth, window.innerHeight);
  return w <= 520 ? 'phone' : window.innerWidth <= 1024 ? 'tablet' : 'desktop';
}

function uuid() {
  return crypto.randomUUID ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
      const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function baseEvent(type) {
  return {
    type, event_id: uuid(), persona, exec_id, deck_id,
    hand_id: `${deck_id}:h${S.hand + 1}`,
    replay: S.replay, ts: new Date().toISOString(),
  };
}

function toast(msg, ms = 1800) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.add('hidden'), ms);
}

// ---------------------------------------------------------------- deck load
async function loadDeck() {
  const cacheKey = `lila_deck_${deck_id}`;
  try {
    const res = await fetch(`${API}/decks/${deck_id}`, { headers: { authorization: `Bearer ${TOKEN}` } });
    if (!res.ok) throw new Error(`deck fetch ${res.status}`);
    const deck = await res.json();
    localStorage.setItem(cacheKey, JSON.stringify(deck));
    return deck;
  } catch (e) {
    const cached = localStorage.getItem(cacheKey);
    if (cached) { toast('playing from the vault (offline)'); return JSON.parse(cached); }
    throw e;
  }
}

// ---------------------------------------------------------------- casino chrome
function dealerSay(line) { $('dealer-line').textContent = line; }
function nextDealerLine() {
  const lines = S.deck.table.dealer_lines;
  dealerSay(lines[S.dealerIdx % lines.length]);
  S.dealerIdx++;
}

function updateHud() {
  $('streak-n').textContent = S.streak;
  const st = $('streak');
  st.classList.toggle('hot', S.streak >= 10 && S.streak < 20);
  st.classList.toggle('inferno', S.streak >= 20);
  $('chips-n').textContent = S.chips;
  $('mult').textContent = `x${multiplier().toFixed(1)}`;
  const played = S.idx;
  const frac = S.cards.length ? played / S.cards.length : 0;
  $('ring-fg').style.strokeDashoffset = String(119.4 * frac);
  $('deck-count').textContent = `${S.cards.length - played} in the shoe`;
}

function multiplier() { return 1 + Math.min(S.streak, 20) / 20; }

function bankChips() {
  // Pays IDENTICALLY for left and right: volume and continuity, never direction.
  S.chips += Math.round(10 * multiplier());
}

function maybeBonus() {
  S.sinceBonus++;
  if (S.sinceBonus >= S.nextBonusIn) {
    const bonus = randInt(15, 40);
    S.chips += bonus;
    S.sinceBonus = 0;
    S.nextBonusIn = randInt(S.deck.table.bonus_interval.min, S.deck.table.bonus_interval.max);
    const reel = $('reel');
    reel.classList.remove('hidden');
    reel.textContent = `[ = = = ]  +${bonus}`;
    sounds.reelTick();
    setTimeout(() => reel.classList.add('hidden'), 900);
  }
}

function confetti(n = 60) {
  const layer = $('confetti-layer');
  const colors = ['#d4af37', '#f7f4ec', '#27ae60', '#c0392b', '#6a4c93'];
  for (let i = 0; i < n; i++) {
    const c = document.createElement('div');
    c.className = 'confetto';
    c.style.left = `${rng() * 100}vw`;
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = `${0.9 + rng() * 1.4}s`;
    c.style.animationDelay = `${rng() * 0.25}s`;
    layer.appendChild(c);
    setTimeout(() => c.remove(), 2800);
  }
}

// ---------------------------------------------------------------- card render
// RENDER PATH: takes only fields that appear on the face. Nothing hidden.
const SEAL_COLORS = { frtib: '#1b4f72', va: '#7d3c98', army: '#1e8449', dhs: '#154360', gsa: '#b03a2e', doe: '#9a7d0a', ssa: '#2874a6', treasury: '#117864', nih: '#6c3483', generic: '#5d6d7e' };

function initials(agency) {
  return agency.split(/\s+/).filter(w => /^[A-Z]/.test(w)).map(w => w[0]).slice(0, 3).join('');
}

function clockChip(card) {
  const c = card.clock || {};
  const label = c.label || '';
  const d = c.days_remaining;
  let cls = '', text = '';
  if (c.label === 'forecast qtr') text = `${c.quarter || 'forecast'}`;
  else if (d == null) text = label;
  else if (d < 0) { text = `${label}`; }
  else { text = `${label} in ${d}d`; cls = d <= 10 ? 'soon' : d <= 25 ? 'mid' : ''; }
  return `<span class="clock-chip ${cls}">&#9200; ${text}${c.date ? ` (${c.date})` : ''}</span>`;
}

function renderCard(card) {
  const el = $('card');
  const rival = card.kind === 'rival_award';
  const dollars = card.dollars != null
    ? `<span class="dollars-chip">$${Number(card.dollars).toLocaleString()}</span>` : '';
  const incumbent = card.incumbent
    ? `<span class="incumbent-chip">incumbent: ${card.incumbent}</span>` : '';
  const contact = card.contact_present
    ? `<span class="contact-dot"></span><span class="contact-label">contact on record</span>` : '';
  el.innerHTML = `
    <div class="card-top">
      <div class="seal" style="background:${SEAL_COLORS[card.seal_key] || SEAL_COLORS.generic}">${initials(card.agency) || 'US'}</div>
      <div><div class="agency">${card.agency}</div><div class="office">${card.office}</div></div>
    </div>
    ${rival ? '<div class="rival-banner">RIVAL AWARD ON RECORD</div>' : ''}
    <div class="card-title">${card.title}</div>
    <div class="basis">&ldquo;${card.basis}&rdquo;</div>
    <div class="card-meta">${clockChip(card)}${dollars}${incumbent}${contact}</div>`;
  el.classList.remove('hidden', 'fly', 'snap');
  el.style.transform = '';
  el.classList.add('dealing');
  setTimeout(() => el.classList.remove('dealing'), 340);
  sounds.deal();
  S.cardShownAt = Date.now();
}

// ---------------------------------------------------------------- gestures
let drag = null;

function attachGestures() {
  const el = $('card');
  const zone = $('card-zone');
  const width = () => el.offsetWidth || 320;

  el.addEventListener('pointerdown', e => {
    if ($('card').classList.contains('hidden')) return;
    drag = { x0: e.clientX, y0: e.clientY, t0: Date.now(), armed: false };
    el.setPointerCapture(e.pointerId);
  });

  el.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = e.clientX - drag.x0;
    const dy = e.clientY - drag.y0;
    drag.dx = dx; drag.dy = dy;
    const lever = $('lever');
    if (dy > 90 && Math.abs(dx) < 60 && superLikeAvailable()) {
      if (!drag.armed) { drag.armed = true; sounds.ratchet(); lever.classList.add('armed'); lever.textContent = 'release for the jackpot'; }
    } else if (drag.armed) {
      drag.armed = false; lever.classList.remove('armed'); leverText();
    }
    el.style.transform = `translate(${dx}px, ${Math.max(0, dy) * 0.4}px) rotate(${dx / 18}deg)`;
    el.classList.toggle('card-glow-right', dx / width() > 0.2);
    el.classList.toggle('card-glow-left', dx / width() < -0.2);
  });

  el.addEventListener('pointerup', e => {
    if (!drag) return;
    const dx = drag.dx || 0;
    const norm = dx / width();
    const dur = Date.now() - drag.t0;
    if (drag.armed) {
      fireSuperLike(dur);
    } else if (Math.abs(norm) >= 0.3) {
      commitSwipe(norm > 0 ? 'right' : 'left', Math.min(1.5, Math.abs(norm)) * Math.sign(norm), dur);
    } else {
      el.classList.add('snap');
      el.style.transform = '';
      el.classList.remove('card-glow-right', 'card-glow-left');
      sounds.snapBack();
    }
    drag = null;
  });

  document.addEventListener('keydown', e => {
    if ($('table').classList.contains('hidden') || !$('chip-row').classList.contains('hidden')) return;
    if (e.key === 'ArrowRight') commitSwipe('right', e.shiftKey ? 0.9 : 0.4, 150);
    if (e.key === 'ArrowLeft') commitSwipe('left', e.shiftKey ? -0.9 : -0.4, 150);
  });
  zone.addEventListener('click', () => {}); // keeps iOS pointer events lively
}

function superLikeAvailable() { return !S.superLikeUsedThisHand; }
function leverText() {
  const lever = $('lever');
  if (superLikeAvailable()) { lever.classList.remove('hidden'); lever.textContent = '\u25bc pull to super like \u25bc'; }
  else lever.classList.add('hidden');
}

// ---------------------------------------------------------------- swipes
const RIGHT_REASONS = ['fit', 'timing', 'money', 'access'];
const LEFT_REASONS = ['wrong category', 'too small', 'closed or dead', 'wrong buyer', 'cannot win'];

function commitSwipe(direction, signedNorm, swipeMs, superLike = false) {
  const el = $('card');
  const card = S.cards[S.idx];
  if (!card) return;
  const msOnCard = Date.now() - S.cardShownAt;

  el.classList.add('fly');
  el.style.transform = `translate(${direction === 'right' ? 130 : -130}%, -8%) rotate(${direction === 'right' ? 22 : -22}deg)`;
  if (direction === 'right') { sounds.right(); sounds.whooshRight(); } else { sounds.left(); sounds.whooshLeft(); }
  pulse(el);

  const now = Date.now();
  S.streak = (now - S.lastSwipeAt < 8000 || S.swipesTotal === 0) ? S.streak + 1 : 1;
  if (S.streak === 1 && S.swipesTotal > 0) sounds.streakHiss();
  if (S.streak === 20) sounds.ember();
  S.lastSwipeAt = now;
  S.bestStreak = Math.max(S.bestStreak, S.streak);
  S.swipesTotal++;
  bankChips();

  const posInDeck = S.idx;
  const hand = S.hands[S.hand];
  const ev = {
    ...baseEvent('swipe'),
    card_id: card.id,
    kind: card.kind,
    direction,
    swipe_distance: Number(signedNorm.toFixed(4)),
    swipe_ms: swipeMs,
    swipe_velocity: Number((Math.abs(signedNorm) / Math.max(swipeMs, 1) * 1000).toFixed(4)),
    intensity_bin: Math.abs(signedNorm) >= 0.55 ? 'strong' : 'lean',
    reason: null,
    ms_on_card: msOnCard,
    position_in_hand: posInDeck - hand.start,
    position_in_deck: posInDeck,
    overlap: !!card.overlap,
    retest: !!card.retest,
    device_class: deviceClass(),
    streak_at_swipe: S.streak,
    session_minute: Number(((now - S.sessionStart) / 60000).toFixed(2)),
    since_bonus_event: S.sinceBonus,
    muted: isMuted(),
  };

  S.decisions.set(card.id, direction);
  if (direction === 'right') S.rightsThisHand.push(card);
  localStorage.setItem(totalKey, String(totalPlayed() + 1));

  if (superLike) {
    ev.swipe_distance = 1.0; ev.intensity_bin = 'strong';
    flusher.record(ev);
    flusher.record({ ...baseEvent('super_like'), card_id: card.id, kind: card.kind, mode: 'immediate' });
    S.superLikeUsedThisHand = true;
    S.superLikesFired++;
    sounds.jackpot();
    confetti(90);
    if (!localStorage.getItem('lila_sl_seen')) {
      toast('Super like: I would call this contact tomorrow.', 2600);
      localStorage.setItem('lila_sl_seen', '1');
    }
    advance();
  } else {
    showChips(direction, ev);
  }
  maybeBonus();
  updateHud();
}

function fireSuperLike(dur) {
  $('lever').classList.remove('armed');
  commitSwipe('right', 1.0, dur, true);
}

function showChips(direction, ev) {
  const row = $('chip-row');
  row.innerHTML = '';
  const reasons = direction === 'right' ? RIGHT_REASONS : LEFT_REASONS;
  let done = false;
  const finish = reason => {
    if (done) return;
    done = true;
    ev.reason = reason;
    flusher.record(ev);
    row.classList.add('hidden');
    advance();
  };
  for (const r of reasons) {
    const b = document.createElement('button');
    b.className = 'reason-chip';
    b.textContent = r;
    b.onclick = () => { sounds.chip(); finish(r); };
    row.appendChild(b);
  }
  row.classList.remove('hidden');
  setTimeout(() => finish(null), 1000); // ignore is a valid label
}

// ---------------------------------------------------------------- flow
function advance() {
  S.idx++;
  const hand = S.hands[S.hand];
  updateHud();
  if (S.idx >= hand.start + hand.size) {
    flusher.flush(); // per-hand flush (locked decision 6)
    showOrdering();
  } else {
    setTimeout(() => { renderCard(S.cards[S.idx]); leverText(); }, 120);
  }
}

function showOrdering() {
  $('table').classList.add('hidden');
  const screen = $('order-screen');
  const list = $('order-list');
  list.innerHTML = '';
  const rights = S.rightsThisHand.slice(-8);
  if (!rights.length) { screen.classList.add('hidden'); return showDuels([]); }
  dealerSay('Stack your chips.');

  let starCard = null;
  const rows = rights.map(card => ({ card }));

  function draw() {
    list.innerHTML = '';
    rows.forEach((row, i) => {
      const li = document.createElement('li');
      const canStar = i === 0 && !S.superLikeUsedThisHand;
      li.innerHTML = `
        <span class="order-pos">${i + 1}</span>
        <span class="order-title">${row.card.title}<br><span class="agency">${row.card.agency}</span>${row.card.kind === 'rival_award' ? ' <span class="rival-banner">RIVAL</span>' : ''}</span>
        <span class="order-move">
          <button data-i="${i}" data-d="-1" ${i === 0 ? 'disabled' : ''}>&#9650;</button>
          <button data-i="${i}" data-d="1" ${i === rows.length - 1 ? 'disabled' : ''}>&#9660;</button>
        </span>
        ${canStar ? `<button class="order-star ${starCard === row.card ? 'lit' : ''}" title="promote to super like">&#11088;</button>` : ''}`;
      li.querySelectorAll('.order-move button').forEach(btn => {
        btn.onclick = () => {
          const from = Number(btn.dataset.i), to = from + Number(btn.dataset.d);
          [rows[from], rows[to]] = [rows[to], rows[from]];
          sounds.chip();
          if (starCard) starCard = rows[0].card === starCard ? starCard : null;
          draw();
        };
      });
      const star = li.querySelector('.order-star');
      if (star) star.onclick = () => { starCard = starCard ? null : rows[0].card; sounds.ratchet(); draw(); };
      list.appendChild(li);
    });
  }
  draw();
  screen.classList.remove('hidden');

  $('order-done').onclick = () => {
    const ranked = rows.map(r => r.card);
    flusher.record({
      ...baseEvent('ordering'),
      ranked_card_ids: ranked.map(c => c.id),
      kinds: ranked.map(c => c.kind),
    });
    if (starCard) {
      flusher.record({ ...baseEvent('super_like'), card_id: starCard.id, kind: starCard.kind, mode: 'retroactive' });
      S.superLikeUsedThisHand = true;
      S.superLikesFired++;
      sounds.jackpot();
      confetti(60);
    }
    sounds.payout(4);
    screen.classList.add('hidden');
    flusher.flush();
    showDuels(rights);
  };
}

function showDuels(rights) {
  const pool = rights.filter(c => true);
  const nDuels = Math.min(S.deck.table.duels_per_hand, Math.floor(pool.length / 2));
  if (nDuels < 1) return endHand();
  const screen = $('duel-screen');
  dealerSay('Heads-up round.');
  const shuffled = pool.slice().sort(() => rng() - 0.5);
  const duels = [];
  for (let i = 0; i + 1 < shuffled.length && duels.length < nDuels; i += 2) {
    duels.push([shuffled[i], shuffled[i + 1]]);
  }
  let di = 0;
  let shownAt = 0;

  function drawDuel() {
    if (di >= duels.length) { screen.classList.add('hidden'); return endHand(); }
    const [a, b] = duels[di];
    const zone = $('duel-cards');
    zone.innerHTML = '';
    sounds.flip();
    for (const [card, other] of [[a, b], [b, a]]) {
      const div = document.createElement('div');
      div.className = 'duel-card';
      div.innerHTML = `
        <div class="agency">${card.agency}</div>
        <div class="card-title">${card.title}</div>
        ${card.kind === 'rival_award' ? '<div class="rival-banner">RIVAL</div>' : ''}
        ${clockChip(card)}`;
      div.onclick = () => {
        sounds.chip();
        flusher.record({
          ...baseEvent('duel'),
          card_a: a.id, card_b: b.id,
          kinds: [a.kind, b.kind],
          winner: card.id,
          sampling_reason: 'recent_rights',
          response_ms: Date.now() - shownAt,
        });
        di++;
        drawDuel();
      };
      zone.appendChild(div);
    }
    shownAt = Date.now();
  }
  $('duel-skip').onclick = () => { di++; drawDuel(); }; // a skipped duel records nothing
  screen.classList.remove('hidden');
  drawDuel();
}

function endHand() {
  S.rightsThisHand = [];
  S.superLikeUsedThisHand = false;
  S.hand++;
  flusher.flush();
  if (S.hand >= S.hands.length || S.idx >= S.cards.length) return showPayout();
  nextDealerLine();
  const bonus = randInt(15, 35);
  S.chips += bonus;
  sounds.reelTick();
  toast(`hand break: +${bonus} chips banked`);
  $('table').classList.remove('hidden');
  setTimeout(() => { renderCard(S.cards[S.idx]); leverText(); updateHud(); }, 400);
}

// ---------------------------------------------------------------- payout
function showPayout() {
  $('table').classList.add('hidden');
  const screen = $('payout');
  dealerSay('Settle up.');
  sounds.payout(10);
  confetti(40);

  const completedKey = 'lila_completed';
  const completed = JSON.parse(localStorage.getItem(completedKey) || '[]');
  if (!completed.includes(deck_id)) {
    completed.push(deck_id);
    localStorage.setItem(completedKey, JSON.stringify(completed));
  }

  const clean = cleanRun(S.deck.cards, S.decisions);
  const t = title(totalPlayed());
  const stats = [
    ['cards played', S.swipesTotal],
    ['longest streak', S.bestStreak],
    ['super likes', S.superLikesFired],
    ['chips banked', S.chips],
  ];
  $('payout-stats').innerHTML = stats.map(([k, v]) =>
    `<div><div class="stat-n" data-target="${v}">0</div><div class="subtle">${k}</div></div>`).join('')
    + `<div style="grid-column:1/-1"><div class="stat-n">${t}</div><div class="subtle">table title${clean ? ' &middot; no dead cards taken' : ''}</div></div>`;

  // slot-payout counter spin
  document.querySelectorAll('#payout-stats .stat-n[data-target]').forEach(el => {
    const target = Number(el.dataset.target);
    let cur = 0;
    const step = Math.max(1, Math.ceil(target / 30));
    const timer = setInterval(() => {
      cur = Math.min(target, cur + step);
      el.textContent = cur;
      if (cur >= target) clearInterval(timer);
    }, 30);
  });

  drawShareTile(t, clean);
  screen.classList.remove('hidden');

  if (NEXT_TOKEN) {
    const btn = $('next-persona');
    btn.classList.remove('hidden');
    btn.onclick = () => {
      location.hash = `t=${NEXT_TOKEN}&api=${encodeURIComponent(API)}`;
      location.reload();
    };
  }
  flusher.flush().then?.(() => {});
  $('sync-note').textContent = navigator.onLine
    ? 'every judgment is on the record'
    : 'offline: judgments are vaulted and will stream when the radio returns';
}

// The share tile contains NO card contents: streak, chips, title, deck date,
// branding only. Executives screenshot and forward these.
function drawShareTile(t, clean) {
  const cv = $('share-tile');
  const g = cv.getContext('2d');
  g.fillStyle = '#0b3d2e'; g.fillRect(0, 0, 600, 340);
  g.strokeStyle = '#d4af37'; g.lineWidth = 4; g.strokeRect(10, 10, 580, 320);
  g.fillStyle = '#d4af37'; g.font = '300 44px system-ui'; g.textAlign = 'center';
  g.fillText('L I L A', 300, 78);
  g.fillStyle = '#f7f4ec'; g.font = '700 30px system-ui';
  g.fillText(`${S.chips} chips  \u00b7  streak ${S.bestStreak}`, 300, 150);
  g.font = '26px system-ui'; g.fillStyle = '#d4af37';
  g.fillText(t + (clean ? '  \u00b7  clean table' : ''), 300, 200);
  g.font = '18px system-ui'; g.fillStyle = 'rgba(247,244,236,.6)';
  g.fillText(`${S.deck.display_name} table \u00b7 pressed ${S.deck.pressed_from_pool}`, 300, 250);
  g.fillText('the federal market, one hand at a time', 300, 290);
}

// ---------------------------------------------------------------- start
async function start() {
  S.deck = await loadDeck();
  S.replay = JSON.parse(localStorage.getItem('lila_completed') || '[]').includes(deck_id);
  S.cards = await displayOrder(display_order_seed, S.deck.cards);
  let acc = 0;
  S.hands = S.deck.hands.map(size => { const h = { start: acc, size }; acc += size; return h; });

  $('role-line').textContent = S.deck.role_line;
  const prior = S.deck.table.prior_exec_count;
  if (prior > 0) {
    const ord = n => n === 1 ? '2nd' : n === 2 ? '3rd' : `${n + 1}th`;
    $('scarcity').textContent = `You are the ${ord(prior)} executive at ${S.deck.client} to play this shoe.`;
  }
  if (S.replay) $('scarcity').textContent += ' (replay: your first read stands; this one is logged separately)';
  dealerSay(S.deck.table.dealer_lines[0]);

  $('start').onclick = () => {
    $('intro').classList.add('hidden');
    $('table').classList.remove('hidden');
    renderCard(S.cards[0]);
    leverText();
    updateHud();
  };
  $('mute').onclick = () => {
    setMuted(!isMuted());
    $('mute').textContent = isMuted() ? '\u{1F507}' : '\u{1F50A}';
  };
  $('mute').textContent = isMuted() ? '\u{1F507}' : '\u{1F50A}';
  $('share').onclick = async () => {
    const cv = $('share-tile');
    cv.toBlob(async blob => {
      const file = new File([blob], 'lila.png', { type: 'image/png' });
      if (navigator.share && navigator.canShare?.({ files: [file] })) {
        try { await navigator.share({ files: [file], title: 'LILA' }); } catch (e) {}
      } else {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = 'lila.png'; a.click();
      }
    });
  };
  attachGestures();

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => {});
  }
  flusher.flush(); // recover anything vaulted from a previous session
}

start().catch(e => {
  document.body.innerHTML = `<p style="padding:40px;text-align:center">The table is dark: ${e.message}. Check your link or your signal.</p>`;
});
