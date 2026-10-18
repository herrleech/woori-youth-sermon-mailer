"""대한성서공회 새번역(SAENEW) 전체를 Firestore bible/{bookNo}_{chapter} 로 저장한다. (1회성, 개인 열람용)

  python import_bible.py --check              # 66권 1장이 모두 파싱되는지만 확인 (저장 안 함)
  python import_bible.py --book 43 --dry-run  # 요한복음만 파싱해서 출력
  python import_bible.py                      # 전체 저장 (이미 있는 장은 건너뜀, 이어하기 가능)
chapters 수는 web/bible.js 의 BOOKS 와 동일해야 한다.
"""
import argparse
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

URL = "https://www.bskorea.or.kr/bible/korbibReadpage.php"
HEADERS = {"User-Agent": "Mozilla/5.0 (personal QT reader)"}

# (bskorea 코드, 장 수) — 정경 순서 66권
BOOKS = [
    ("gen", 50), ("exo", 40), ("lev", 27), ("num", 36), ("deu", 34), ("jos", 24), ("jdg", 21), ("rut", 4),
    ("1sa", 31), ("2sa", 24), ("1ki", 22), ("2ki", 25), ("1ch", 29), ("2ch", 36), ("ezr", 10), ("neh", 13),
    ("est", 10), ("job", 42), ("psa", 150), ("pro", 31), ("ecc", 12), ("sng", 8), ("isa", 66), ("jer", 52),
    ("lam", 5), ("ezk", 48), ("dan", 12), ("hos", 14), ("jol", 3), ("amo", 9), ("oba", 1), ("jnh", 4),
    ("mic", 7), ("nam", 3), ("hab", 3), ("zep", 3), ("hag", 2), ("zec", 14), ("mal", 4),
    ("mat", 28), ("mrk", 16), ("luk", 24), ("jhn", 21), ("act", 28), ("rom", 16), ("1co", 16), ("2co", 13),
    ("gal", 6), ("eph", 6), ("php", 4), ("col", 4), ("1th", 5), ("2th", 3), ("1ti", 6), ("2ti", 4),
    ("tit", 3), ("phm", 1), ("heb", 13), ("jas", 5), ("1pe", 5), ("2pe", 3), ("1jn", 5), ("2jn", 1),
    ("3jn", 1), ("jud", 1), ("rev", 22),
]


def fetch_chapter(code, ch, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(URL, params={"version": "SAENEW", "book": code, "chap": ch, "sec": 1},
                             headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return parse(r.text)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{code} {ch}: {last}")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    box = soup.select_one("div.bible_read")
    if not box:
        raise ValueError("bible_read not found")
    for x in box.select("div.D2, a.comment"):  # 각주 팝업/각주 번호 제거
        x.decompose()
    verses = {}
    for n in box.select("span.number"):
        num = int(re.sub(r"\D", "", n.get_text()) or 0)
        sp = n.parent
        n.extract()
        t = re.sub(r"\s+", " ", sp.get_text()).strip()
        if num and t:
            verses[num] = (verses.get(num, "") + " " + t).strip()
    if not verses:
        raise ValueError("no verses")
    last = max(verses)
    return [verses.get(i, "") for i in range(1, last + 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--book", type=int, help="책 번호(1~66)만")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--delay", type=float, default=0.8)
    a = ap.parse_args()

    if a.check:
        bad = 0
        for no, (code, _) in enumerate(BOOKS, 1):
            try:
                v = fetch_chapter(code, 1)
                print(f"{no:2d} {code} ok ({len(v)}절)")
            except Exception as e:  # noqa: BLE001
                bad += 1
                print(f"{no:2d} {code} FAIL {e}", file=sys.stderr)
            time.sleep(a.delay)
        sys.exit(1 if bad else 0)

    db = None
    if not a.dry_run:
        import firebase_admin
        from firebase_admin import credentials, firestore

        raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if not raw:
            sys.exit("FIREBASE_SERVICE_ACCOUNT 환경변수가 없습니다")
        firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
        db = firestore.client()

    failed = []
    for no, (code, chapters) in enumerate(BOOKS, 1):
        if a.book and a.book != no:
            continue
        for ch in range(1, chapters + 1):
            doc = None if a.dry_run else db.collection("bible").document(f"{no}_{ch}")
            if doc is not None and not a.force and doc.get().exists:
                continue
            try:
                verses = fetch_chapter(code, ch)
            except Exception as e:  # noqa: BLE001
                print(f"[FAIL] {e}", file=sys.stderr)
                failed.append((no, ch))
                continue
            if a.dry_run:
                print(f"{no}_{ch}: {len(verses)}절", verses[:2])
            else:
                doc.set({"book": no, "chapter": ch, "verses": verses, "version": "SAENEW"})
                print(f"[OK] {no}_{ch} {len(verses)}절")
            time.sleep(a.delay)
    if failed:
        print("실패한 장(다시 실행하면 이어서 채웁니다):", failed, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
