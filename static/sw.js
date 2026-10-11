const CACHE_NAME = 'pisynapse-v57';
// Browser scope: the SPA is served at /static/ (root / redirects there).
// The native WebView never registers this service worker (JS gates on _NATIVE).
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/apple-touch-icon.png',
  '/static/icons/favicon.ico',
  '/static/fonts/dm-sans-latin.woff2',
  '/static/fonts/dm-sans-latin-ext.woff2',
  '/static/vendor/marked.min.js',
  '/static/vendor/dompurify.min.js',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.allSettled(STATIC_ASSETS.map(url => cache.add(url).catch(() => {})))
    )
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // ALLOWLIST (week-2): only same-origin shell assets are ever cached.
  // Everything else — every current AND future API route — goes straight
  // to the network, so a new endpoint can never be forgotten in a deny
  // list. (The failure mode behind the staleness bug: /users was missing
  // from the old never-cache list, and auth-dependent responses were
  // served stale from the cache.)
  if (request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return;
  const cacheable = url.pathname === '/' || url.pathname === '/favicon.ico'
    || url.pathname.startsWith('/static/');
  if (!cacheable) return;

  // Documents: NETWORK-FIRST — the app must never render a stale HTML shell.
  // Cache only as an offline fallback.
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      }).catch(() => caches.match(request))
    );
    return;
  }

  // Other GET assets: stale-while-revalidate
  event.respondWith(
    caches.match(request).then(cached => {
      const fetchPromise = fetch(request).then(response => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
        }
        return response;
      }).catch(() => cached);

      return cached || fetchPromise;
    })
  );
});
