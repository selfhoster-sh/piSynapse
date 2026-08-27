const CACHE_NAME = 'pisynapse-v45';
const STATIC_ASSETS = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/fonts/dm-sans-latin.woff2',
  '/static/fonts/dm-sans-latin-ext.woff2',
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

  // Never cache API calls or non-GET requests
  if (request.method !== 'GET' || url.pathname.startsWith('/chat') ||
      url.pathname.startsWith('/config') || url.pathname.startsWith('/widget') ||
      url.pathname === '/health') {
    return;
  }

  event.respondWith(
    caches.match(request).then(cached => {
      // Return cached version, but also fetch fresh copy in background
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
