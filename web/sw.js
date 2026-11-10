// Cache só do "casco" do app (cache-first). A API nunca é cacheada.
const V = "dumpbox-v2", CASCO = ["/", "/app.js", "/manifest.webmanifest", "/icon.svg"];
self.addEventListener("install", e => e.waitUntil(caches.open(V).then(c => c.addAll(CASCO))));
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.pathname.startsWith("/api/")) return;
  e.respondWith(fetch(e.request).then(r => { caches.open(V).then(c => c.put(e.request, r.clone())); return r; })
    .catch(() => caches.match(e.request)));
});
