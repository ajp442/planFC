{% load static %}// Bump CACHE_VERSION whenever the shell assets change. A service worker that
// serves a stale shell forever is the classic PWA failure, and it is invisible
// in development because you are always hard-reloading.
const CACHE_VERSION = "planfc-v4";

const OFFLINE_URL = "{% url 'offline' %}";

const SHELL = [
  "{% static 'css/app.css' %}",
  "{% static 'js/app.js' %}",
  "{% static icon_dir|add:'icon_192.png' %}",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) =>
      Promise.all([
        cache.addAll(SHELL),
        // Without cookies, so the cached copy never carries the name of
        // whoever happened to be signed in when the worker installed.
        fetch(new Request(OFFLINE_URL, { credentials: "omit" })).then((response) =>
          cache.put(OFFLINE_URL, response)
        ),
      ])
    )
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

// The server marks every page a signed-in member sees as no-store
// (accounts/middleware.py). Cache Storage belongs to the browser, not to
// whoever is signed in, so storing those would let the next person on the
// phone read them offline.
function isCacheable(response) {
  const cacheControl = response.headers.get("Cache-Control") || "";
  return response.ok && response.type === "basic" && !/no-store|private/.test(cacheControl);
}

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Only GETs are cacheable, and a ledger must never serve a POST from cache.
  if (request.method !== "GET") return;

  // Network-first for pages so members never see yesterday's game list, with
  // the cache as the offline fallback. Private pages are never cached, so
  // offline they fall back to the offline page.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (isCacheable(response)) {
            const copy = response.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request).then((hit) => hit || caches.match(OFFLINE_URL)))
    );
    return;
  }

  // Cache-first for static assets, which are versioned by the cache name.
  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request))
  );
});

// --- Push notifications ------------------------------------------------------
// accounts/push.py sends {title, body, url}. The worker runs even when the app
// is closed, which is the whole point: the push service wakes it to show this.

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (error) {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "{{ app_name|escapejs }}", {
      body: data.body || "",
      icon: "{% static icon_dir|add:'icon_192.png' %}",
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  // Only ever open our own pages, whatever URL the message carried.
  const target = new URL(event.notification.data.url || "/", self.location.origin);
  const url = target.origin === self.location.origin ? target.href : self.location.origin + "/";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      // Reuse an open window of the app rather than stacking up new ones.
      for (const client of windows) {
        if ("focus" in client) {
          return client.focus().then((focused) => (focused && "navigate" in focused ? focused.navigate(url) : focused));
        }
      }
      return self.clients.openWindow(url);
    })
  );
});
