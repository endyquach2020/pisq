const CACHE_NAME = 'pisq-exam-shell-v5';
const APP_SHELL = ['/', '/exam', '/static/css/style.css', '/static/images/logo_school.png'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(cacheNames => Promise.all(
        cacheNames
          .filter(cacheName => cacheName.startsWith('pisq-exam-shell-') && cacheName !== CACHE_NAME)
          .map(cacheName => caches.delete(cacheName))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const requestUrl = new URL(request.url);
  if (request.method !== 'GET' || requestUrl.origin !== self.location.origin) return;
  if (requestUrl.pathname.startsWith('/api/')) return;

  if (request.mode === 'navigate') {
    const cacheKey = new Request(`${requestUrl.origin}${requestUrl.pathname}`);
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok && ['/', '/exam'].includes(requestUrl.pathname)) {
            const cachedResponse = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(cacheKey, cachedResponse));
          }
          return response;
        })
        .catch(async () => {
          const cachedPage = await caches.match(cacheKey);
          if (cachedPage) return cachedPage;
          if (requestUrl.pathname !== '/exam') throw new Error('Offline page is not cached.');
          const examPage = await caches.match('/exam');
          if (examPage) return examPage;
          throw new Error('Exam shell is not cached.');
        })
    );
    return;
  }

  if (requestUrl.pathname.startsWith('/static/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const cachedResponse = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, cachedResponse));
          }
          return response;
        })
        .catch(async () => {
          const cachedAsset = await caches.match(request);
          if (cachedAsset) return cachedAsset;
          throw new Error('Requested asset is not cached.');
        })
    );
  }
});
