// 앱 셸 + 라이브러리를 미리 캐시해서 비행기 모드에서도 앱이 열린다. Firestore 요청은 가로채지 않는다
// (Firestore 자체 오프라인 캐시가 데이터를 보관한다).
const CACHE = "qt-shell-v14";
const SHELL = [
  "./", "index.html", "style.css", "app.js", "store.js", "bible.js", "firebase-config.js", "manifest.webmanifest",
  "vendor/quill.js", "vendor/quill.snow.css",
  "vendor/firebase/firebase-app.js", "vendor/firebase/firebase-auth.js", "vendor/firebase/firebase-firestore.js",
  "icons/icon-192.png", "icons/icon-512.png", "icons/icon.svg",
];
const EXTERNAL = ["i.ytimg.com"]; // 설교 썸네일: 한 번 본 것은 오프라인에서도 표시

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
  if (!same && !EXTERNAL.includes(url.hostname)) return;
  const nav = req.mode === "navigate";
  const stable = !same || url.pathname.includes("/vendor/"); // 바뀌지 않는 파일은 캐시 우선
  e.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(req, { ignoreSearch: nav });
      if (stable && hit) return hit;
      // 앱 파일은 네트워크 우선(배포 즉시 반영), 오프라인이면 캐시
      try {
        const res = await fetch(req, same ? { cache: "no-cache" } : undefined);
        if (res.ok || res.type === "opaque") cache.put(req, res.clone());
        return res;
      } catch (err) {
        if (hit) return hit;
        if (nav) { const shell = await cache.match("./", { ignoreSearch: true }); if (shell) return shell; }
        throw err;
      }
    })
  );
});

// ───── 푸시 알림 ─────
// 서버(메일러/스케줄)가 FCM 으로 보낸 data 메시지를 받아 알림으로 보여준다. (알림 내용은 title/body/hash/tag)
self.addEventListener("push", (e) => {
  let d = {};
  try { const j = e.data ? e.data.json() : {}; d = j.data || j; } catch { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "한 구절 묵상", {
    body: d.body || "", icon: "icons/icon-192.png", badge: "icons/icon-192.png",
    tag: d.tag || undefined, data: { hash: d.hash || "#/" },
  }));
});
// 알림을 누르면: 열려 있는 앱 창이 있으면 그 창을 해당 화면으로, 없으면 새로 연다
self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  const hash = (e.notification.data && e.notification.data.hash) || "#/";
  e.waitUntil((async () => {
    const wins = await clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) {
      if ("focus" in w) { await w.focus(); w.postMessage({ type: "navigate", hash }); return; }
    }
    await clients.openWindow("./" + hash);
  })());
});
