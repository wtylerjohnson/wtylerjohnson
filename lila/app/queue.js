// Offline-first telemetry queue. IndexedDB is the source of truth; events
// stay queued until the server acknowledges them. Flush triggers: end of each
// hand, queue length 10, the online event, visibilitychange to hidden.
// On pagehide a sendBeacon carries whatever remains; beaconed events STAY in
// the queue (no response is readable) and the server dedupes on event_id.

const DB_NAME = 'lila_queue';
const STORE = 'events';

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'event_id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx(mode, fn) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const result = fn(t.objectStore(STORE));
    t.oncomplete = () => resolve(result.result !== undefined ? result.result : result);
    t.onerror = () => reject(t.error);
  });
}

export async function enqueue(event) {
  await tx('readwrite', s => s.put(event));
}

export async function pending() {
  return tx('readonly', s => s.getAll());
}

async function remove(ids) {
  await tx('readwrite', s => { ids.forEach(id => s.delete(id)); return { result: true }; });
}

export function makeFlusher(apiBase, token, onStatus) {
  let flushing = false;

  async function flush() {
    if (flushing || !navigator.onLine) return;
    flushing = true;
    try {
      const events = await pending();
      if (events.length) {
        const res = await fetch(`${apiBase}/events`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
          body: JSON.stringify({ events }),
        });
        if (res.ok) {
          await remove(events.map(e => e.event_id));
          onStatus && onStatus({ sent: events.length, queued: 0 });
        }
      } else {
        onStatus && onStatus({ sent: 0, queued: 0 });
      }
    } catch (e) {
      const q = await pending();
      onStatus && onStatus({ sent: 0, queued: q.length, offline: true });
    } finally {
      flushing = false;
    }
  }

  async function record(event) {
    await enqueue(event);
    const q = await pending();
    onStatus && onStatus({ queued: q.length, offline: !navigator.onLine });
    if (q.length >= 10) flush();
  }

  function beacon() {
    pending().then(events => {
      if (events.length && navigator.sendBeacon) {
        // Beacon cannot set headers; the token rides as a query param.
        navigator.sendBeacon(
          `${apiBase}/events?t=${encodeURIComponent(token)}`,
          new Blob([JSON.stringify({ events })], { type: 'application/json' })
        );
      }
    });
  }

  window.addEventListener('online', flush);
  document.addEventListener('visibilitychange', () => { if (document.hidden) flush(); });
  window.addEventListener('pagehide', beacon);

  return { flush, record, beacon };
}
