// 데이터 계층: Firebase(실시간 동기화) 또는 로컬 데모 모드(localStorage)
import { firebaseConfig } from "./firebase-config.js";

export const isFirebase = !!firebaseConfig.apiKey && !new URLSearchParams(location.search).has("demo"); // ?demo 로 열면 로컬 데모 모드
const FB = "https://www.gstatic.com/firebasejs/10.14.1/";

export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

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
    subscribeEntries: (cb) => sub(mine("qtEntries"), cb),
    subscribeNotes: (cb) => sub(mine("notes"), cb),
    saveEntry: (date, patch) =>
      F.setDoc(F.doc(mine("qtEntries"), date), { ...patch, updatedAt: F.serverTimestamp() }, { merge: true }),
    saveNote: (id, patch) =>
      F.setDoc(F.doc(mine("notes"), id), { ...patch, updatedAt: F.serverTimestamp() }, { merge: true }),
    deleteNote: (id) => F.deleteDoc(F.doc(mine("notes"), id)),
    async getChapter(bookNo, ch) {
      const s = await F.getDoc(F.doc(db, "bible", `${bookNo}_${ch}`));
      return s.exists() ? s.data().verses : null;
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
    subscribeEntries: (cb) => reg(subs.entries, () => list(entries()), cb),
    subscribeNotes: (cb) => reg(subs.notes, () => list(notes()), cb),
    async saveEntry(date, patch) {
      const e = entries();
      e[date] = { ...e[date], ...patch, updatedAt: Date.now() };
      LSset("qt.entries", e);
      emit();
    },
    async saveNote(id, patch) {
      const n = notes();
      n[id] = { ...n[id], ...patch, updatedAt: Date.now() };
      LSset("qt.notes", n);
      emit();
    },
    async deleteNote(id) {
      const n = notes();
      delete n[id];
      LSset("qt.notes", n);
      emit();
    },
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
