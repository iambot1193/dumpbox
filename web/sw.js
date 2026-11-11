// Casco do app: rede primeiro (revalida por ETag), cache só quando offline. A API nunca é cacheada.
const V = "dumpbox-v17", CASCO = ["/", "/app.js", "/manifest.webmanifest", "/icon.svg", "/fonts/barlow-500.woff2", "/fonts/barlow-700.woff2"];
self.addEventListener("install", e => { self.skipWaiting(); e.waitUntil(caches.open(V).then(c => c.addAll(CASCO))); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
  .then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.pathname.startsWith("/api/")) return;
  // no-cache: sem isso o navegador usa cache heurístico (servidor não manda Cache-Control) e a tela fica velha
  e.respondWith(fetch(u.href, { cache: "no-cache" }).then(r => { caches.open(V).then(c => c.put(e.request, r.clone())); return r; })
    .catch(() => caches.match(e.request)));
});
