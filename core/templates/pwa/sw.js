{% load static %}// Bump CACHE_VERSION whenever the shell assets change. A service worker that
// serves a stale shell forever is the classic PWA failure, and it is invisible
// in development because you are always hard-reloading.
const CACHE_VERSION = "planfc-v2";

const SHELL = [
  "{% static 'css/app.css' %}",
  "{% static 'js/app.js' %}",
  "{% static 'icons/icon_192.png' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Only GETs are cacheable, and a ledger must never serve a POST from cache.
  if (request.method !== "GET") return;

  // Network-first for pages so members never see yesterday's game list, with
  // the cache as the offline fallback.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
    );
    return;
  }

  // Cache-first for static assets, which are versioned by the cache name.
  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request))
  );
});
