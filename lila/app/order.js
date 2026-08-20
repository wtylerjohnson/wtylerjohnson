// Per-exec display order. MIRRORS lila/deck/common.py byte-for-byte:
// hash-sort ids by sha256(seed + ":" + id), then spread salt so no two salt
// cards sit adjacent when avoidable. Change both files or neither.

async function sha256hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

export async function hashOrder(seedHex, ids) {
  const keyed = await Promise.all(ids.map(async id => [await sha256hex(seedHex + ':' + id), id]));
  keyed.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
  return keyed.map(k => k[1]);
}

export function spreadSalt(cards) {
  cards = cards.slice();
  let i = 1;
  while (i < cards.length) {
    if (cards[i].salt && cards[i - 1].salt) {
      let j = i + 1;
      while (j < cards.length && cards[j].salt) j++;
      if (j >= cards.length) break;
      [cards[i], cards[j]] = [cards[j], cards[i]];
    }
    i++;
  }
  return cards;
}

export async function displayOrder(doSeed, cards) {
  const byId = Object.fromEntries(cards.map(c => [c.id, c]));
  const ids = await hashOrder(doSeed, Object.keys(byId).sort());
  return spreadSalt(ids.map(i => byId[i]));
}

// Aggregate-only salt reveal for the payout screen ("no dead cards taken").
// House rule 2: per-card correctness is NEVER revealed; this returns one
// boolean for the whole session and lives outside every render path.
export function cleanRun(cards, decisions) {
  const salts = cards.filter(c => c.salt && decisions.has(c.id));
  if (!salts.length) return false;
  return salts.every(c => decisions.get(c.id) === 'left');
}
