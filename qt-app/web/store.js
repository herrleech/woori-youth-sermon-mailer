// 데이터 계층: Firebase(실시간 동기화) 또는 로컬 데모 모드(localStorage)
import { firebaseConfig } from "./firebase-config.js";

export const isFirebase = !!firebaseConfig.apiKey && !new URLSearchParams(location.search).has("demo"); // ?demo 로 열면 로컬 데모 모드
const FB = "./vendor/firebase/"; // Firebase JS SDK 10.14.1 (오프라인에서도 열리도록 앱에 포함)

export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

// ── 웹 푸시 도우미 ──
export const urlB64ToBytes = (s) => {
  const p = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  return Uint8Array.from(atob(p), (c) => c.charCodeAt(0));
};
export const endpointId = async (endpoint) =>
  [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(endpoint)))].map((b) => b.toString(16).padStart(2, "0")).join("");
const sameBytes = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);

let impl;

// ───────────────────────── Firebase ─────────────────────────
async function makeFirebase() {
  const [{ initializeApp }, A, F] = await Promise.all([
    import(FB + "firebase-app.js"),
    import(FB + "firebase-auth.js"),
    import(FB + "firebase-firestore.js"),
  ]);
  const app = initializeApp(firebaseConfig);
  const auth = A.getAuth(app);
  const db = F.initializeFirestore(app, {
    localCache: F.persistentLocalCache({ tabManager: F.persistentMultipleTabManager() }),
  });
  let uid = null;
  const mine = (sub) => F.collection(db, "users", uid, sub);
  const sub = (q, cb) => F.onSnapshot(q, (s) => cb(s.docs.map((d) => ({ id: d.id, ...d.data() }))));

  return {
    onAuth(cb) {
      return A.onAuthStateChanged(auth, (u) => {
        uid = u ? u.uid : null;
        cb(u ? { uid: u.uid, name: u.displayName, email: u.email } : null);
      });
    },
    signIn: () => A.signInWithPopup(auth, new A.GoogleAuthProvider()),
    signOut: () => A.signOut(auth),
    subscribeQt: (cb) => sub(F.query(F.collection(db, "qt"), F.orderBy("date", "desc")), cb),
    subscribeSermons: (cb) => sub(F.query(F.collection(db, "sermons"), F.orderBy("published", "desc")), cb), // 메일러가 채운다
    subscribeEntries: (cb) => sub(mine("qtEntries"), cb),
    subscribeNotes: (cb) => sub(mine("notes"), cb),
    saveEntry: (date, patch) =>
      F.setDoc(F.doc(mine("qtEntries"), date), { ...patch, updatedAt: F.serverTimestamp() }, { merge: true }),
    saveNote: (id, patch, at) =>
      F.setDoc(F.doc(mine("notes"), id), { ...patch, updatedAt: at ? F.Timestamp.fromMillis(at) : F.serverTimestamp() }, { merge: true }),
    deleteNote: (id) => F.deleteDoc(F.doc(mine("notes"), id)),
    async getChapter(bookNo, ch) {
      const s = await F.getDoc(F.doc(db, "bible", `${bookNo}_${ch}`));
      return s.exists() ? s.data().verses : null;
    },
    // ── 푸시 알림: 표준 웹 푸시(VAPID). 기기마다 users/{uid}/devices/{구독 해시} 문서를 두고, 서버가 이 구독으로 직접 보낸다 ──
    // (Firebase 메시징 SDK 의 토큰 등록 API 를 거치지 않는다: 그 API 가 401 로 거부되는 문제를 피한다)
    push: {
      async supported() { return "Notification" in window && "serviceWorker" in navigator && "PushManager" in window; },
      permission: () => ("Notification" in window ? Notification.permission : "unsupported"),
      token: () => { try { return localStorage.getItem("qt.pushId") || ""; } catch { return ""; } },
      async device(id) {
        const s = await F.getDoc(F.doc(mine("devices"), id));
        return s.exists() ? s.data() : null;
      },
      async subscription(vapidKey) {                  // 현재 서버 키로 구독 (예전 키로 만든 구독이면 새로 만든다)
        const reg = await navigator.serviceWorker.ready;
        const want = urlB64ToBytes(vapidKey);
        let sub = await reg.pushManager.getSubscription();
        if (sub) {
          const have = sub.options && sub.options.applicationServerKey;
          if (!have || !sameBytes(new Uint8Array(have), want)) { await sub.unsubscribe(); sub = null; }
        }
        return sub || reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: want });
      },
      async register(vapidKey, prefs) {                // 권한 요청 + 구독 + 기기 등록
        if ((await Notification.requestPermission()) !== "granted") throw new Error("알림 권한이 허용되지 않았습니다");
        const j = (await this.subscription(vapidKey)).toJSON();
        const id = await endpointId(j.endpoint);
        await F.setDoc(F.doc(mine("devices"), id), { endpoint: j.endpoint, keys: j.keys, ...prefs, ua: navigator.userAgent.slice(0, 120), updatedAt: F.serverTimestamp() }, { merge: true });
        try { localStorage.setItem("qt.pushId", id); } catch { /* ignore */ }
        return id;
      },
      savePrefs: (id, prefs) => F.setDoc(F.doc(mine("devices"), id), { ...prefs, updatedAt: F.serverTimestamp() }, { merge: true }),
      async refresh(vapidKey) {                        // 앱을 열 때 구독이 바뀌었으면 새 구독으로 옮긴다 (설정은 유지)
        const old = this.token();
        if (!old || Notification.permission !== "granted") return;
        const j = (await this.subscription(vapidKey)).toJSON();
        const id = await endpointId(j.endpoint);
        const prev = id === old ? null : await this.device(old).catch(() => null);
        await F.setDoc(F.doc(mine("devices"), id), { ...(prev || {}), endpoint: j.endpoint, keys: j.keys, updatedAt: F.serverTimestamp() }, { merge: true });
        if (id !== old) {
          await F.deleteDoc(F.doc(mine("devices"), old)).catch(() => {});
          try { localStorage.setItem("qt.pushId", id); } catch { /* ignore */ }
        }
      },
      async unregister() {
        const id = this.token();
        try { const sub = await (await navigator.serviceWorker.ready).pushManager.getSubscription(); if (sub) await sub.unsubscribe(); } catch { /* ignore */ }
        if (id) await F.deleteDoc(F.doc(mine("devices"), id)).catch(() => {});
        try { localStorage.removeItem("qt.pushId"); } catch { /* ignore */ }
      },
    },
  };
}

// ───────────────────────── 로컬 데모 ─────────────────────────
const LS = (k, d) => {
  try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; }
};
const LSset = (k, v) => localStorage.setItem(k, JSON.stringify(v));

function makeLocal() {
  const subs = { entries: new Set(), notes: new Set(), qt: new Set() };
  const entries = () => LS("qt.entries", {});
  const notes = () => LS("qt.notes", {});
  const emit = () => {
    subs.entries.forEach((f) => f());
    subs.notes.forEach((f) => f());
  };
  window.addEventListener("storage", emit); // 다른 탭 변경 → 즉시 반영(동기화 시연)
  const list = (o) => Object.entries(o).map(([id, v]) => ({ id, ...v }));
  const reg = (set, get, cb) => {
    const f = () => cb(get());
    set.add(f);
    f();
    return () => set.delete(f);
  };
  let demoQt = null;
  return {
    onAuth(cb) { setTimeout(() => cb({ uid: "local", name: "로컬 데모", email: "" }), 0); return () => {}; },
    signIn: async () => {},
    signOut: async () => {},
    subscribeQt(cb) {
      (demoQt ? Promise.resolve(demoQt) : fetch("demo/qt.json").then((r) => r.json())).then((d) => {
        demoQt = d;
        cb(d);
      }).catch(() => cb([]));
      return () => {};
    },
    subscribeSermons(cb) {
      fetch("demo/sermons.json").then((r) => r.json()).then((d) => cb(d.map((s) => ({ id: s.video_id, ...s })))).catch(() => cb([]));
      return () => {};
    },
    subscribeEntries: (cb) => reg(subs.entries, () => list(entries()), cb),
    subscribeNotes: (cb) => reg(subs.notes, () => list(notes()), cb),
    async saveEntry(date, patch) {
      const e = entries();
      e[date] = { ...e[date], ...patch, updatedAt: Date.now() };
      LSset("qt.entries", e);
      emit();
    },
    async saveNote(id, patch, at) {
      const n = notes();
      n[id] = { ...n[id], ...patch, updatedAt: at || Date.now() };
      LSset("qt.notes", n);
      emit();
    },
    async deleteNote(id) {
      const n = notes();
      delete n[id];
      LSset("qt.notes", n);
      emit();
    },
    push: { supported: async () => false, permission: () => "unsupported", token: () => "", refresh: async () => {} },
    async getChapter(bookNo, ch) {
      const all = await fetch("demo/bible.json").then((r) => r.json()).catch(() => ({}));
      return all[`${bookNo}_${ch}`] || null;
    },
  };
}

export async function getStore() {
  if (!impl) impl = isFirebase ? await makeFirebase() : makeLocal();
  return impl;
}
