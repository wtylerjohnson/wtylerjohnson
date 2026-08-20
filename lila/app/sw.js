// Offline shell. Cache-first for the app shell, network-first with cache
// fallback for deck fetches. Telemetry never goes through here; the
// IndexedDB queue in queue.js is the source of truth for events.

const SHELL = 'lila-shell-v1';
const SHELL_FILES = ['.', 'index.html', 'styles.css', 'app.js', 'order.js', 'audio.js', 'queue.js', 'manifest.webmanifest', 'icon.svg'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(SHELL).then(c => c.addAll(SHELL_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET') return; // events POST passes straight through
  if (url.pathname.includes('/decks/')) {
    e.respondWith(
      fetch(e.request).then(res => {
        const copy = res.clone();
        caches.open('lila-decks').then(c => c.put(e.request, copy));
        return res;
      }).catch(() => caches.match(e.request))
    );
    return;
  }
  e.respondWith(caches.match(e.request).then(hit => hit || fetch(e.request)));
});
