// 앱 셸 캐시 (stale-while-revalidate). Firestore/Storage 요청은 가로채지 않는다.
const CACHE = "qt-shell-v6";
const CDN = ["cdn.jsdelivr.net", "www.gstatic.com"];
const SHELL = ["./", "index.html", "style.css", "app.js", "store.js", "bible.js", "firebase-config.js", "manifest.webmanifest"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  const same = url.origin === location.origin;
  if (!same && !CDN.includes(url.hostname)) return;
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(req);
      // 앱 파일은 네트워크 우선(배포 즉시 반영), 오프라인이면 캐시. CDN 라이브러리는 캐시 우선.
      if (!same && hit) return hit;
      try {
        const res = await fetch(req, same ? { cache: "no-cache" } : undefined);
        if (res.ok || res.type === "opaque") cache.put(req, res.clone());
        return res;
      } catch (err) {
        if (hit) return hit;
        throw err;
      }
    })
  );
});
