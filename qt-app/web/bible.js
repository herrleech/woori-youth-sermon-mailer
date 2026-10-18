// 성경 책 표, 구절 파서 (요3:16 / 요 3:16-18 / 롬8:1~4 / 시편 23편 1절 ...)
export const BOOKS = [
  ["창세기", ["창"], 50], ["출애굽기", ["출"], 40], ["레위기", ["레"], 27], ["민수기", ["민"], 36],
  ["신명기", ["신"], 34], ["여호수아", ["수"], 24], ["사사기", ["삿"], 21], ["룻기", ["룻"], 4],
  ["사무엘상", ["삼상"], 31], ["사무엘하", ["삼하"], 24], ["열왕기상", ["왕상"], 22], ["열왕기하", ["왕하"], 25],
  ["역대상", ["대상"], 29], ["역대하", ["대하"], 36], ["에스라", ["스"], 10], ["느헤미야", ["느"], 13],
  ["에스더", ["에"], 10], ["욥기", ["욥"], 42], ["시편", ["시"], 150], ["잠언", ["잠"], 31],
  ["전도서", ["전"], 12], ["아가", ["아"], 8], ["이사야", ["사"], 66], ["예레미야", ["렘"], 52],
  ["예레미야애가", ["애"], 5], ["에스겔", ["겔"], 48], ["다니엘", ["단"], 12], ["호세아", ["호"], 14],
  ["요엘", ["욜"], 3], ["아모스", ["암"], 9], ["오바댜", ["옵"], 1], ["요나", ["욘"], 4],
  ["미가", ["미"], 7], ["나훔", ["나"], 3], ["하박국", ["합"], 3], ["스바냐", ["습"], 3],
  ["학개", ["학"], 2], ["스가랴", ["슥"], 14], ["말라기", ["말"], 4],
  ["마태복음", ["마"], 28], ["마가복음", ["막"], 16], ["누가복음", ["눅"], 24], ["요한복음", ["요"], 21],
  ["사도행전", ["행"], 28], ["로마서", ["롬"], 16], ["고린도전서", ["고전"], 16], ["고린도후서", ["고후"], 13],
  ["갈라디아서", ["갈"], 6], ["에베소서", ["엡"], 6], ["빌립보서", ["빌"], 4], ["골로새서", ["골"], 4],
  ["데살로니가전서", ["살전"], 5], ["데살로니가후서", ["살후"], 3], ["디모데전서", ["딤전"], 6],
  ["디모데후서", ["딤후"], 4], ["디도서", ["딛"], 3], ["빌레몬서", ["몬"], 1], ["히브리서", ["히"], 13],
  ["야고보서", ["약"], 5], ["베드로전서", ["벧전"], 5], ["베드로후서", ["벧후"], 3], ["요한일서", ["요일"], 5],
  ["요한이서", ["요이"], 1], ["요한삼서", ["요삼"], 1], ["유다서", ["유"], 1], ["요한계시록", ["계"], 22],
].map(([name, abbr, chapters], i) => ({ no: i + 1, name, abbr, chapters }));

// 이름/약어 → 책 (긴 이름 우선 매칭하기 위해 길이 내림차순)
const NAME_MAP = new Map();
for (const b of BOOKS) {
  NAME_MAP.set(b.name, b);
  for (const a of b.abbr) NAME_MAP.set(a, b);
}
const NAMES = [...NAME_MAP.keys()].sort((a, b) => b.length - a.length);
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const REF_SRC = `(${NAMES.map(esc).join("|")})\\s?(\\d{1,3})\\s?(?:[:.장편])\\s?(\\d{1,3})(?:\\s?[-~–]\\s?(\\d{1,3}))?절?`;

const HANGUL = /[가-힣]/;

/** 텍스트에서 유효한 구절 참조를 모두 찾는다. -> [{index, length, ref}] */
export function findRefs(text) {
  const re = new RegExp(REF_SRC, "g");
  const out = [];
  let m;
  while ((m = re.exec(text))) {
    const prev = text[m.index - 1];
    const next = text[m.index + m[0].length];
    if (prev && HANGUL.test(prev)) continue; // '사요3:16' 같은 단어 중간
    if (next && /\d/.test(next)) continue;
    const ref = normalize(m[1], +m[2], +m[3], m[4] ? +m[4] : null);
    if (ref) out.push({ index: m.index, length: m[0].length, ref: ref.key });
  }
  return out;
}

function normalize(bookName, ch, v1, v2) {
  const b = NAME_MAP.get(bookName);
  if (!b || ch < 1 || ch > b.chapters || v1 < 1) return null;
  if (v2 !== null && v2 < v1) v2 = null;
  return { book: b, ch, v1, v2, key: `${b.no}:${ch}:${v1}${v2 ? "-" + v2 : ""}` };
}

/** 'bookNo:ch:v1[-v2]' -> 객체 */
export function decodeRef(key) {
  const m = /^(\d+):(\d+):(\d+)(?:-(\d+))?$/.exec(key || "");
  if (!m) return null;
  const book = BOOKS[+m[1] - 1];
  return { book, ch: +m[2], v1: +m[3], v2: m[4] ? +m[4] : null };
}

export function refLabel(r) {
  if (r.v1 === 1 && r.v2 === 999) return `${r.book.name} ${r.ch}장`;
  return `${r.book.name} ${r.ch}:${r.v1}${r.v2 ? "-" + r.v2 : ""}`;
}

/** 본문 입력칸용: '요3:16-18, 롬8:1' 또는 장 전체 '요3' / '시편 23편' -> ref key 배열 */
export function parsePassage(str) {
  const keys = findRefs(str || "").map((m) => m.ref);
  if (keys.length) return keys;
  const m = new RegExp(`^\\s*(${NAMES.map(esc).join("|")})\\s?(\\d{1,3})\\s?[장편]?\\s*$`).exec(str || "");
  const b = m && NAME_MAP.get(m[1]);
  return b && +m[2] >= 1 && +m[2] <= b.chapters ? [`${b.no}:${+m[2]}:1-999`] : [];
}

/** 텍스트 앞부분의 책 이름 -> 책 (예: '베드로전서 4장' / '벧전 4') */
export function bookOfText(str) {
  const s = (str || "").trim();
  for (const n of NAMES) if (s.startsWith(n)) return NAME_MAP.get(n);
  return null;
}

/** 필터 입력(예: '벧전 4', '요3:16', '요한복음') 해석 -> {book, ch?} */
export function parseFilter(str) {
  const s = (str || "").trim();
  const b = bookOfText(s);
  if (!b) return null;
  const rest = s.slice(NAMES.find((n) => s.startsWith(n)).length);
  const m = /^\s*(\d{1,3})/.exec(rest);
  return { book: b, ch: m ? +m[1] : null };
}

export const DELIMS = /[\s,.;:!?)\]”’"'·]/;
