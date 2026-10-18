import { getStore, isFirebase, newId } from "./store.js";
import { BOOKS, findRefs, decodeRef, refLabel, bookOfText, parseFilter, parsePassage, DELIMS } from "./bible.js";

const $ = (s, r = document) => r.querySelector(s);
const view = $("#view");
const esc = (s = "") => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const DOW = "일월화수목금토";
const fmtDate = (d) => {
  const [y, m, dd] = d.split("-");
  return `${y}.${m}.${dd}(${DOW[new Date(+y, +m - 1, +dd).getDay()]})`;
};
const ls = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } },
};
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.hidden = true), 2000);
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
  }
  toast("복사했습니다");
}
const debounce = (fn, ms) => { let t; const w = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; w.flush = () => { clearTimeout(t); }; return w; };

// ───────────── 상태 ─────────────
let store;
let qtList = [];
let entries = new Map();
let notes = [];
const listeners = new Set();           // 데이터 변경 시 현재 뷰에 알림
const notify = () => listeners.forEach((f) => f());
const syncDot = $("#sync");
const setSync = (s) => { syncDot.className = "sync " + s; };

const filter = { q: "", from: "", to: "", verse: "", open: false, mode: ls.get("qt.mode", "card") };

// ───────────── 라우터 ─────────────
let cleanup = null;
function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const h = location.hash.replace(/^#/, "") || "/";
  const [, a, b] = h.split("/");
  document.querySelectorAll("[data-nav]").forEach((n) => n.classList.toggle("active",
    (n.dataset.nav === "home" && (!a || a === "qt")) || (n.dataset.nav === "notes" && (a === "notes" || a === "note"))));
  window.scrollTo(0, 0);
  if (a === "qt" && b) cleanup = renderDetail(decodeURIComponent(b));
  else if (a === "notes") cleanup = renderNotes();
  else if (a === "note" && b) cleanup = renderNote(decodeURIComponent(b));
  else cleanup = renderHome();
}
window.addEventListener("hashchange", route);

// ───────────── 대시보드 ─────────────
function chapterOf(passage) { const m = /(\d+)\s*장/.exec(passage || ""); return m ? +m[1] : null; }

function matches(qt) {
  if (filter.from && qt.date < filter.from) return false;
  if (filter.to && qt.date > filter.to) return false;
  if (filter.verse.trim()) {
    const pf = parseFilter(filter.verse);
    if (pf) {
      const b = bookOfText(qt.passage);
      if (!b || b.no !== pf.book.no) return false;
      if (pf.ch && chapterOf(qt.passage) !== pf.ch) return false;
    } else if (!(`${qt.passage} ${qt.verseRef}`).includes(filter.verse.trim())) return false;
  }
  const q = filter.q.trim().toLowerCase();
  if (q) {
    const e = entries.get(qt.date) || {};
    const hay = [qt.title, qt.passage, qt.verseRef, qt.summary, qt.meditation, qt.verseKrv, qt.verseNew, qt.prayer,
      (qt.questions || []).join(" "), e.godMessage, e.application].join(" ").toLowerCase();
    if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
  }
  return true;
}

function renderHome() {
  view.innerHTML = `
    <div class="bar">
      <input id="f-q" class="grow" type="search" placeholder="키워드 검색 (제목·본문·묵상·내 기록)" value="${esc(filter.q)}">
      <button id="f-toggle" class="btn small ${filter.open ? "on" : ""}">필터</button>
      <button id="m-card" class="btn small ${filter.mode === "card" ? "on" : ""}" title="카드뷰">▦ 카드</button>
      <button id="m-list" class="btn small ${filter.mode === "list" ? "on" : ""}" title="리스트뷰">☰ 리스트</button>
    </div>
    <div id="filters" class="filters ${filter.open ? "open" : ""}">
      <label>시작일<input id="f-from" type="date" value="${filter.from}"></label>
      <label>종료일<input id="f-to" type="date" value="${filter.to}"></label>
      <label>말씀 구절<input id="f-verse" list="books" placeholder="예: 베드로전서 4 / 요3" value="${esc(filter.verse)}"></label>
      <datalist id="books">${BOOKS.map((b) => `<option value="${b.name}">`).join("")}</datalist>
      <button id="f-reset" class="btn small" style="align-self:end">초기화</button>
    </div>
    <div id="count" class="count"></div>
    <div id="cards"></div>`;
  const draw = () => {
    const rows = qtList.filter(matches);
    $("#count").textContent = `${rows.length}개 / 전체 ${qtList.length}개`;
    const box = $("#cards");
    box.className = "cards" + (filter.mode === "list" ? " list" : "");
    if (!rows.length) { box.innerHTML = `<div class="empty">${qtList.length ? "조건에 맞는 묵상이 없습니다" : "아직 수집된 묵상이 없습니다"}</div>`; return; }
    box.innerHTML = rows.map((qt) => {
      const e = entries.get(qt.date);
      const done = e && (e.godMessage || e.application) ? `<span class="done">✓ 기록함</span>` : "";
      return `<a class="card" href="#/qt/${qt.date}">
        <div class="meta"><div class="date">${fmtDate(qt.date)}</div></div>
        <div class="body">${done}<h3>${esc(qt.title)}</h3><div class="ref">${esc(qt.verseRef || qt.passage)}</div>
        <p class="sum">${esc(qt.summary)}</p></div></a>`;
    }).join("");
  };
  const bind = (id, key, ev = "input") => $(id).addEventListener(ev, (e) => { filter[key] = e.target.value; draw(); });
  bind("#f-q", "q"); bind("#f-from", "from", "change"); bind("#f-to", "to", "change"); bind("#f-verse", "verse");
  $("#f-toggle").onclick = (e) => { filter.open = !filter.open; $("#filters").classList.toggle("open", filter.open); e.target.classList.toggle("on", filter.open); };
  const setMode = (m) => { filter.mode = m; ls.set("qt.mode", m); $("#m-card").classList.toggle("on", m === "card"); $("#m-list").classList.toggle("on", m === "list"); draw(); };
  $("#m-card").onclick = () => setMode("card");
  $("#m-list").onclick = () => setMode("list");
  $("#f-reset").onclick = () => { Object.assign(filter, { q: "", from: "", to: "", verse: "" }); renderHome(); };
  listeners.add(draw);
  draw();
  return () => listeners.delete(draw);
}

// ───────────── QT 상세 ─────────────
const COLORS = { y: "노랑", g: "초록", p: "분홍", b: "파랑" };
const BLOCKS = [
  ["summary", "본문 개요"], ["verseKrv", "오늘의 한 구절 · 개역개정"], ["verseNew", "오늘의 한 구절 · 새번역"], ["meditation", "한 구절 묵상"],
];
const LABEL = { summary: "본문 개요", verseKrv: "개역개정", verseNew: "새번역", meditation: "한 구절 묵상" };

function markup(text, hls) {
  const cols = new Array(text.length).fill(null);
  for (const h of hls) for (let i = Math.max(0, h.s); i < Math.min(text.length, h.e); i++) cols[i] = h.c;
  let out = "", i = 0;
  while (i < text.length) {
    let j = i;
    while (j < text.length && cols[j] === cols[i]) j++;
    const seg = esc(text.slice(i, j));
    out += cols[i] ? `<mark class="${cols[i]}">${seg}</mark>` : seg;
    i = j;
  }
  return out;
}
function subtract(hls, k, s, e) {
  const out = [];
  for (const h of hls) {
    if (h.k !== k || h.e <= s || h.s >= e) { out.push(h); continue; }
    if (h.s < s) out.push({ ...h, e: s });
    if (h.e > e) out.push({ ...h, s: e });
  }
  return out;
}

// 본문/구절 텍스트를 팝업 링크 버튼으로 (인식 실패 시 일반 텍스트). hl: 장 팝업에서 강조할 구절 텍스트
function refBtn(label, hl) {
  const k = parsePassage(label)[0];
  if (!k) return esc(label);
  const h = hl ? parsePassage(hl)[0] || "" : "";
  return `<button class="reflink" data-ref="${k}" data-hl="${h}" title="새번역으로 보기">📖 ${esc(label)}</button>`;
}

function renderDetail(date) {
  const idx = qtList.findIndex((q) => q.date === date);
  const qt = qtList[idx];
  if (!qt) {
    view.innerHTML = `<div class="empty">${qtList.length ? "해당 날짜의 묵상이 없습니다" : "불러오는 중…"}<br><a href="#/">목록으로</a></div>`;
    const retry = () => { if (qtList.find((q) => q.date === date)) route(); };
    listeners.add(retry);
    return () => listeners.delete(retry);
  }
  const older = qtList[idx + 1], newer = qtList[idx - 1];
  const text = (k) => qt[k] || "";
  view.innerHTML = `
    <div class="detail">
      <div class="page-head">
        <a class="btn small" href="#/">← 목록</a>
        <span class="date">${fmtDate(qt.date)}</span>
        <span style="margin-left:auto;display:flex;gap:6px">
          ${older ? `<a class="btn small" href="#/qt/${older.date}">‹ 이전</a>` : ""}
          ${newer ? `<a class="btn small" href="#/qt/${newer.date}">다음 ›</a>` : ""}
        </span>
      </div>
      <h1>${esc(qt.title)}</h1>
      <div class="ref">${refBtn(qt.passage, qt.verseRef)} · ${refBtn(qt.verseRef)}</div>
      ${BLOCKS.map(([k, label]) => text(k) ? `<section class="sec"><h2>${label}</h2><div class="txt" data-k="${k}"></div></section>` : "").join("")}
      <section class="sec"><h2>묵상질문</h2><div class="txt">${esc((qt.questions || []).join("\n\n"))}</div></section>
      <section class="sec"><h2>심정이 통하는 기도</h2><div class="txt">${esc(qt.prayer)}</div></section>
      <section class="sec input">
        <h2>오늘 하나님이 나에게 하시는 메시지</h2>
        <textarea id="in-god" placeholder="말씀을 통해 하나님이 내게 하시는 말씀은…"></textarea>
        <h2 style="margin-top:12px">오늘 하루 어떻게 적용할까</h2>
        <textarea id="in-app" placeholder="오늘 하루 구체적으로 순종할 한 가지는…"></textarea>
        <div id="savestate" class="savestate"></div>
      </section>
      <p><a href="${esc(qt.sourceUrl)}" target="_blank" rel="noopener">원문 보기 ↗</a></p>
    </div>
    <div class="toolbar">
      ${Object.keys(COLORS).map((c) => `<button class="dot ${c}" data-hl="${c}" title="${COLORS[c]} 하이라이트"></button>`).join("")}
      <button class="btn small" data-hl="">하이라이트 지우기</button>
      <button class="btn small" id="b-copy">복사</button>
      <button class="btn small primary" id="b-quote">인용 복사</button>
    </div>`;

  view.querySelectorAll(".reflink").forEach((b) => b.addEventListener("click", () => openVerse(b.dataset.ref, b.dataset.hl)));
  const entry = () => entries.get(date) || {};
  const drawBlocks = () => {
    const hls = entry().highlights || [];
    view.querySelectorAll(".txt[data-k]").forEach((el) => {
      const k = el.dataset.k;
      el.innerHTML = markup(text(k), hls.filter((h) => h.k === k));
    });
  };
  drawBlocks();

  // 입력 자동저장 + 원격 반영
  const god = $("#in-god"), app = $("#in-app"), st = $("#savestate");
  let dirty = false;
  const save = debounce(async () => {
    setSync("busy"); st.textContent = "저장 중…";
    try {
      await store.saveEntry(date, { godMessage: god.value, application: app.value });
      dirty = false; st.textContent = "저장됨"; setSync("ok");
    } catch (e) { st.textContent = "저장 실패: " + e.message; setSync("err"); }
  }, 800);
  const onInput = () => { dirty = true; st.textContent = "입력 중…"; save(); };
  god.addEventListener("input", onInput); app.addEventListener("input", onInput);
  const pull = () => {
    const e = entry();
    if (!dirty) {
      if (document.activeElement !== god || god.value !== (e.godMessage || "")) { if (!dirty) god.value = e.godMessage || ""; }
      if (document.activeElement !== app || app.value !== (e.application || "")) { if (!dirty) app.value = e.application || ""; }
    }
    drawBlocks();
  };
  pull();
  listeners.add(pull);

  // 선택 → 하이라이트/복사/인용
  let sel = null;
  const onSel = () => {
    const s = document.getSelection();
    if (!s || s.isCollapsed || !s.rangeCount) return;
    const r = s.getRangeAt(0);
    const el = (r.commonAncestorContainer.nodeType === 1 ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement)?.closest(".txt");
    if (!el || !view.contains(el)) return;
    const pre = document.createRange();
    pre.selectNodeContents(el); pre.setEnd(r.startContainer, r.startOffset);
    const s0 = pre.toString().length;
    const str = r.toString();
    sel = { k: el.dataset.k || null, s: s0, e: s0 + str.length, str };
  };
  document.addEventListener("selectionchange", onSel);
  const keep = (e) => e.preventDefault();
  view.querySelectorAll(".toolbar button").forEach((b) => b.addEventListener("mousedown", keep));

  view.querySelectorAll("[data-hl]").forEach((b) => b.addEventListener("click", async () => {
    if (!sel || !sel.k) return toast("하이라이트할 본문을 먼저 선택하세요");
    let hls = subtract([...(entry().highlights || [])], sel.k, sel.s, sel.e);
    if (b.dataset.hl) hls.push({ k: sel.k, s: sel.s, e: sel.e, c: b.dataset.hl });
    entries.set(date, { ...entry(), highlights: hls });
    drawBlocks();
    document.getSelection()?.removeAllRanges();
    try { await store.saveEntry(date, { highlights: hls }); setSync("ok"); } catch { setSync("err"); }
  }));
  $("#b-copy").onclick = () => { if (!sel?.str) return toast("복사할 본문을 먼저 선택하세요"); copyText(sel.str.trim()); };
  $("#b-quote").onclick = () => {
    if (!sel?.str) return toast("인용할 본문을 먼저 선택하세요");
    const ver = sel.k === "verseKrv" || sel.k === "verseNew" ? `${qt.verseRef} ${LABEL[sel.k]}` : `${LABEL[sel.k] || ""} · 분당우리교회 한 구절 묵상 ${fmtDate(date)}`;
    copyText(`“${sel.str.trim()}”\n— ${ver}`);
  };

  return () => {
    save.flush();
    if (dirty) store.saveEntry(date, { godMessage: god.value, application: app.value });
    listeners.delete(pull);
    document.removeEventListener("selectionchange", onSel);
  };
}

// ───────────── 설교 메모 목록 ─────────────
let noteQ = "";
function renderNotes() {
  view.innerHTML = `
    <div class="bar">
      <input id="n-q" class="grow" type="search" placeholder="메모 검색" value="${esc(noteQ)}">
      <button id="n-new" class="btn primary small">＋ 새 메모</button>
    </div>
    <div id="n-count" class="count"></div><div id="n-list" class="cards list"></div>`;
  const draw = () => {
    const q = noteQ.trim().toLowerCase();
    const rows = notes.filter((n) => !q || `${n.title} ${n.passage || ""} ${n.preview}`.toLowerCase().includes(q))
      .sort((a, b) => ts(b.updatedAt) - ts(a.updatedAt));
    $("#n-count").textContent = `${rows.length}개`;
    $("#n-list").innerHTML = rows.length ? rows.map((n) => `<a class="card" href="#/note/${n.id}">
      <div class="meta"><div class="date">${n.updatedAt ? new Date(ts(n.updatedAt)).toLocaleDateString("ko-KR") : ""}</div></div>
      <div class="body"><h3>${esc(n.title || "제목 없음")}</h3>${n.passage ? `<div class="ref">${esc(n.passage)}</div>` : ""}<p class="sum">${esc(n.preview || "")}</p></div></a>`).join("")
      : `<div class="empty">설교 메모가 없습니다. 새 메모를 만들어 보세요.</div>`;
  };
  $("#n-q").addEventListener("input", (e) => { noteQ = e.target.value; draw(); });
  $("#n-new").onclick = () => { location.hash = "#/note/" + newId(); };
  listeners.add(draw); draw();
  return () => listeners.delete(draw);
}
const ts = (v) => (v && v.toMillis ? v.toMillis() : typeof v === "number" ? v : 0);

// ───────────── 설교 메모 에디터 ─────────────
let quillReady = false;
function setupQuill() {
  if (quillReady) return;
  quillReady = true;
  const Size = Quill.import("attributors/style/size");
  Size.whitelist = ["12px", "14px", "16px", "18px", "20px", "24px", "28px", "32px"];
  Quill.register(Size, true);
  const Inline = Quill.import("blots/inline");
  class VerseBlot extends Inline {
    static blotName = "verse"; static tagName = "span"; static className = "verse";
    static create(v) { const n = super.create(); n.setAttribute("data-ref", v); return n; }
    static formats(n) { return n.getAttribute("data-ref"); }
  }
  Quill.register(VerseBlot);
}


function renderNote(id) {
  setupQuill();
  const sizes = ["12px", "14px", "16px", "18px", "20px", "24px", "28px", "32px"];
  view.innerHTML = `
    <div class="page-head"><a class="btn small" href="#/notes">← 목록</a>
      <span id="n-state" class="savestate" style="margin-left:auto"></span>
      <button id="n-del" class="btn small ghost">삭제</button></div>
    <input id="n-title" class="note-title" placeholder="설교 제목" maxlength="200">
    <div class="passage-row">
      <input id="n-passage" class="passage-input" placeholder="본문 (예: 요3:16-18 / 롬8 / 시편 23편)" maxlength="200">
      <span id="n-chips" class="chips"></span>
    </div>
    <div id="editor-wrap">
      <div id="toolbar">
        <span class="ql-formats">
          <button class="ql-undo txt" title="실행 취소 (Ctrl+Z)">↶</button><button class="ql-redo txt" title="다시 실행">↷</button>
        </span>
        <span class="ql-formats"><select class="ql-size">${sizes.map((s) => `<option value="${s}" ${s === "16px" ? "selected" : ""}>${s}</option>`).join("")}</select></span>
        <span class="ql-formats"><button class="ql-bold"></button><button class="ql-italic"></button><button class="ql-underline"></button><button class="ql-strike"></button></span>
        <span class="ql-formats"><select class="ql-color"></select><select class="ql-background" title="형광펜"></select></span>
        <span class="ql-formats"><button class="ql-list" value="ordered"></button><button class="ql-list" value="bullet"></button><button class="ql-indent" value="+1"></button></span>
        <span class="ql-formats"><button class="ql-clean"></button></span>
      </div>
      <div id="editor"></div>
    </div>
    <p class="count">팁: <b>요3:16</b> 처럼 입력하고 띄어쓰기하면 구절이 링크가 되어 새번역 본문을 팝업으로 볼 수 있어요. 줄 처음에 <b>1.</b> 또는 <b>-</b> 를 치면 목록이 됩니다.</p>`;

  const stEl = $("#n-state"), titleEl = $("#n-title"), passEl = $("#n-passage"), chipsEl = $("#n-chips");
  const busy = (on) => { stEl.textContent = on ? "저장 중…" : "저장됨"; setSync(on ? "busy" : "ok"); };

  const quill = new Quill("#editor", {
    theme: "snow",
    placeholder: "설교를 들으며 메모하세요…",
    modules: {
      toolbar: {
        container: "#toolbar",
        handlers: {
          undo() { this.quill.history.undo(); },
          redo() { this.quill.history.redo(); },
        },
      },
      history: { delay: 500, maxStack: 300, userOnly: true },
    },
  });

  // 구절 자동 링크
  const linkify = () => {
    const ops = quill.getContents().ops; let pos = 0;
    for (const op of ops) {
      const len = typeof op.insert === "string" ? op.insert.length : 1;
      if (op.attributes?.verse && typeof op.insert === "string") {
        const r = findRefs(op.insert);
        if (!(r.length === 1 && r[0].index === 0 && r[0].length === len && r[0].ref === op.attributes.verse)) quill.formatText(pos, len, "verse", false, "api");
      }
      pos += len;
    }
    for (const m of findRefs(quill.getText())) {
      if (quill.getFormat(m.index, m.length).verse !== m.ref) quill.formatText(m.index, m.length, "verse", m.ref, "api");
    }
  };

  let current = null, dirty = false, lastJson = "";
  const doSave = debounce(async () => {
    const delta = JSON.stringify(quill.getContents());
    busy(true);
    try {
      await store.saveNote(id, { title: titleEl.value, passage: passEl.value, delta, preview: quill.getText().replace(/\s+/g, " ").trim().slice(0, 140) });
      lastJson = delta; dirty = false; busy(false);
    } catch (e) { stEl.textContent = "저장 실패: " + e.message; setSync("err"); }
  }, 800);
  const touch = () => { dirty = true; stEl.textContent = "입력 중…"; doSave(); };
  quill.on("text-change", (d, o, source) => {
    if (source === "user") {
      const typed = d.ops.some((op) => typeof op.insert === "string" && (DELIMS.test(op.insert.slice(-1)) || op.insert.includes("\n")));
      if (typed) linkify();
    }
    if (source !== "silent") touch();
  });
  titleEl.addEventListener("input", touch);

  // 본문 입력 → 칩 표시, 입력 확정(Enter/포커스 이동) 시 새번역 팝업
  const drawChips = () => {
    const keys = parsePassage(passEl.value);
    chipsEl.innerHTML = keys.map((k) => `<button class="chip" data-ref="${k}">📖 ${esc(refLabel(decodeRef(k)))}</button>`).join("")
      || (passEl.value.trim() ? `<span class="hint">인식된 구절이 없어요 (예: 요3:16)</span>` : "");
    return keys;
  };
  let shown = "";
  passEl.addEventListener("input", () => { drawChips(); touch(); });
  passEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); passEl.blur(); } });
  passEl.addEventListener("change", () => {
    const keys = drawChips();
    if (keys.length && passEl.value !== shown) { shown = passEl.value; openVerse(keys[0]); }
  });
  chipsEl.addEventListener("click", (e) => { const c = e.target.closest(".chip"); if (c) openVerse(c.dataset.ref); });

  // 구절 클릭 → 팝업
  quill.root.addEventListener("click", (e) => {
    const v = e.target.closest?.(".verse");
    if (v) { e.preventDefault(); openVerse(v.getAttribute("data-ref")); }
  });

  // 원격 반영 (편집 중 로컬 변경이 없을 때만)
  const pull = () => {
    const n = notes.find((x) => x.id === id);
    if (!n) return;
    if (n.title !== undefined && !dirty && document.activeElement !== titleEl) titleEl.value = n.title || "";
    if (!dirty && document.activeElement !== passEl && passEl.value !== (n.passage || "")) { passEl.value = n.passage || ""; shown = passEl.value; drawChips(); }
    if (!n.delta || dirty || n.delta === lastJson) { current = n; return; }
    const sel = quill.getSelection();
    try { quill.setContents(JSON.parse(n.delta), "silent"); } catch { return; }
    lastJson = n.delta; current = n;
    if (sel) quill.setSelection(Math.min(sel.index, quill.getLength() - 1), 0, "silent");
    if (!current.__init) { current.__init = true; linkify(); }
  };
  listeners.add(pull);
  pull();
  if (!current) { titleEl.focus(); }

  $("#n-del").onclick = async () => {
    if (!confirm("이 메모를 삭제할까요?")) return;
    dirty = false; doSave.flush();
    await store.deleteNote(id); location.hash = "#/notes";
  };
  return () => {
    listeners.delete(pull);
    if (dirty) { doSave.flush(); store.saveNote(id, { title: titleEl.value, passage: passEl.value, delta: JSON.stringify(quill.getContents()), preview: quill.getText().replace(/\s+/g, " ").trim().slice(0, 140) }); }
  };
}

// ───────────── 구절 팝업 (새번역) ─────────────
let sheetPlain = "";
async function openVerse(key, hlKey) {
  const r = decodeRef(key);
  if (!r) return;
  const sheet = $("#sheet");
  $("#sheet-copy").style.display = "";
  $("#sheet-title").textContent = `${refLabel(r)} · 새번역`;
  $("#sheet-text").textContent = "불러오는 중…";
  sheet.hidden = false;
  try {
    const verses = await store.getChapter(r.book.no, r.ch);
    if (!verses) { $("#sheet-text").textContent = "이 장의 새번역 본문이 아직 저장되어 있지 않습니다."; sheetPlain = ""; return; }
    const end = Math.min(r.v2 || r.v1, verses.length, r.v1 + 199);
    const parts = [];
    for (let v = r.v1; v <= end; v++) if (verses[v - 1]) parts.push([v, verses[v - 1]]);
    if (!parts.length) { $("#sheet-text").textContent = `${r.ch}장에는 ${r.v1}절이 없습니다.`; sheetPlain = ""; return; }
    const hl = hlKey && decodeRef(hlKey);
    const on = (v) => hl && hl.ch === r.ch && v >= hl.v1 && v <= (hl.v2 || hl.v1);
    $("#sheet-text").innerHTML = parts.map(([v, t]) => `<div class="v${on(v) ? " hl" : ""}" data-v="${v}"><sup>${v}</sup>${esc(t)}</div>`).join("");
    const first = $("#sheet-text .hl");
    if (first) requestAnimationFrame(() => first.scrollIntoView({ block: "center" }));
    sheetPlain = `${refLabel(r)} (새번역)\n` + parts.map(([v, t]) => `${v} ${t}`).join("\n");
  } catch (e) { $("#sheet-text").textContent = "불러오지 못했습니다: " + e.message; }
}
$("#sheet-close").onclick = () => ($("#sheet").hidden = true);
$("#sheet").addEventListener("click", (e) => { if (e.target.id === "sheet") $("#sheet").hidden = true; });
$("#sheet-copy").onclick = () => sheetPlain && copyText(sheetPlain);

// ───────────── 백업: JSON 내보내기 / 가져오기 ─────────────
const stamp = () => new Date().toISOString().slice(0, 10);
function exportData() {
  const data = {
    app: "qt-app", version: 1, exportedAt: new Date().toISOString(),
    notes: notes.map((n) => {
      let delta = null;
      try { delta = JSON.parse(n.delta); } catch { /* 빈 메모 */ }
      return { id: n.id, title: n.title || "", passage: n.passage || "", delta, updatedAt: ts(n.updatedAt) || null };
    }),
    qtEntries: [...entries.values()].map((e) => ({
      date: e.id, highlights: e.highlights || [], godMessage: e.godMessage || "", application: e.application || "", updatedAt: ts(e.updatedAt) || null,
    })),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `qt-backup-${stamp()}.json` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`메모 ${data.notes.length}개 · QT 기록 ${data.qtEntries.length}개를 내보냈습니다`);
}

const hash = (s) => { let h = 5381; for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0; return h.toString(36); };
const pick = (o, keys) => { for (const k of keys) if (o[k] != null && o[k] !== "") return o[k]; return ""; };
const toMs = (v) => { if (typeof v === "number") return v < 1e12 ? v * 1000 : v; const t = Date.parse(v); return Number.isNaN(t) ? 0 : t; };

// 어떤 형태의 JSON이든 {notes, entries} 로 정규화 (우리 형식 + 흔한 필드명)
function normalizeImport(json) {
  let rawNotes = [], rawEntries = [];
  if (Array.isArray(json)) rawNotes = json;
  else if (json && typeof json === "object") {
    rawNotes = json.notes || json.memos || json.sermons || json.items || json.data || [];
    rawEntries = json.qtEntries || [];
    if (!Array.isArray(rawNotes)) rawNotes = Object.values(rawNotes);
    if (!rawNotes.length && !rawEntries.length) { const arr = Object.values(json).find(Array.isArray); if (arr) rawNotes = arr; }
  }
  const tmp = document.createElement("div");
  setupQuill();
  const q = new Quill(tmp);
  const toDelta = (n) => {
    let d = n.delta;
    if (typeof d === "string") { try { d = JSON.parse(d); } catch { d = null; } }
    if (d && Array.isArray(d.ops)) return d;
    if (Array.isArray(d)) return { ops: d };
    const body = String(pick(n, ["html", "content", "body", "text", "memo", "note", "contents", "description"]) || "");
    if (/<[a-z][\s\S]*>/i.test(body)) return q.clipboard.convert({ html: body });
    return { ops: [{ insert: body.endsWith("\n") ? body : body + "\n" }] };
  };
  const outNotes = rawNotes.filter((n) => n && typeof n === "object").map((n) => {
    const delta = toDelta(n);
    const title = String(pick(n, ["title", "name", "subject", "heading"]));
    const passage = String(pick(n, ["passage", "verse", "scripture", "bible", "bibleVerse", "본문"]));
    const at = toMs(pick(n, ["updatedAt", "modifiedAt", "updated", "date", "createdAt", "created"]));
    const plain = (delta.ops || []).map((o) => (typeof o.insert === "string" ? o.insert : "")).join("");
    const id = String(n.id || "imp_" + hash(title + "|" + passage + "|" + plain.slice(0, 300)));
    return { id, patch: { title, passage, delta: JSON.stringify(delta), preview: plain.replace(/\s+/g, " ").trim().slice(0, 140) }, at };
  });
  const outEntries = rawEntries.filter((e) => e && /^\d{4}-\d{2}-\d{2}$/.test(e.date || e.id || ""))
    .map((e) => ({ date: e.date || e.id, patch: { highlights: e.highlights || [], godMessage: e.godMessage || "", application: e.application || "" } }));
  return { notes: outNotes, entries: outEntries };
}

async function importFile(file) {
  let json;
  try { json = JSON.parse(await file.text()); } catch { return toast("JSON 파일을 읽을 수 없습니다"); }
  let data;
  try { data = normalizeImport(json); } catch (e) { return toast("형식을 해석하지 못했습니다: " + e.message); }
  if (!data.notes.length && !data.entries.length) return toast("가져올 메모를 찾지 못했습니다");
  if (!confirm(`메모 ${data.notes.length}개, QT 기록 ${data.entries.length}개를 가져올까요?\n(같은 ID의 기존 항목은 덮어씁니다)`)) return;
  setSync("busy");
  let ok = 0, fail = 0;
  for (let i = 0; i < data.notes.length; i += 20) {
    await Promise.all(data.notes.slice(i, i + 20).map((n) => store.saveNote(n.id, n.patch, n.at || 0).then(() => ok++, () => fail++)));
  }
  for (const e of data.entries) await store.saveEntry(e.date, e.patch).then(() => ok++, () => fail++);
  setSync(fail ? "err" : "ok");
  toast(`가져오기 완료: ${ok}개${fail ? `, 실패 ${fail}개` : ""}`);
}

function openBackup() {
  $("#sheet-title").textContent = "백업 · 가져오기/내보내기";
  $("#sheet-copy").style.display = "none";
  $("#sheet-text").innerHTML = `
    <p>내 설교 메모와 QT 기록(하이라이트·메시지·적용)을 JSON 파일로 저장하거나, 다른 앱의 JSON 메모를 가져옵니다.</p>
    <p><button id="bk-export" class="btn primary">⤓ 내보내기</button>
       <button id="bk-import" class="btn">⤒ 가져오기</button></p>
    <p class="hint">가져오기: 이 앱의 백업 파일, 또는 제목·내용 필드가 있는 메모 목록 JSON. 사진·파일 첨부는 지원하지 않습니다.</p>`;
  $("#sheet").hidden = false;
  $("#bk-export").onclick = exportData;
  $("#bk-import").onclick = () => {
    const i = Object.assign(document.createElement("input"), { type: "file", accept: "application/json,.json" });
    i.onchange = () => i.files[0] && importFile(i.files[0]);
    i.click();
  };
}

// ───────────── 시작 ─────────────
async function boot() {
  store = await getStore();
  $("#btn-login").onclick = () => store.signIn().catch((e) => toast("로그인 실패: " + e.message));
  $("#btn-logout").onclick = () => store.signOut();
  $("#btn-backup").onclick = openBackup;
  let unsubs = [];
  store.onAuth((user) => {
    unsubs.forEach((u) => u && u()); unsubs = [];
    $("#login").hidden = !!user;
    $("#app").hidden = !user;
    $("#btn-logout").hidden = !isFirebase;
    if (!user) return;
    setSync("ok");
    unsubs.push(store.subscribeQt((l) => { qtList = [...l].sort((a, b) => (a.date < b.date ? 1 : -1)); notify(); }));
    unsubs.push(store.subscribeEntries((l) => { entries = new Map(l.map((e) => [e.id, e])); notify(); }));
    unsubs.push(store.subscribeNotes((l) => { notes = l; notify(); }));
    route();
  });
}
boot();
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
