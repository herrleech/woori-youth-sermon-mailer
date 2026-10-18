"""분당우리교회 '한 구절 묵상'을 가져와 Firestore qt/{YYYY-MM-DD} 에 저장한다.

사용:
  python fetch_qt.py --dry-run              # 오늘 것 파싱만 하고 출력
  python fetch_qt.py                        # 오늘 것 저장 (FIREBASE_SERVICE_ACCOUNT 필요)
  python fetch_qt.py --date 2026-10-10      # 특정 날짜
  python fetch_qt.py --backfill 30          # 오늘부터 과거 30일 채우기
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE = "https://www.woorichurch.org/modu/ov/ov_meditation.asp"
KST = timezone(timedelta(hours=9))
HEADERS = {"User-Agent": "Mozilla/5.0 (personal QT reader)"}


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def fetch_html(date, tries=3):
    last = None
    for i in range(tries):
        try:
            r = requests.get(BASE, params={"ov_date": date}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"fetch failed for {date}: {last}")


def _text(el):
    for br in el.find_all("br"):
        br.replace_with("\n")
    t = el.get_text()
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n[ \t]*", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def parse(html, date):
    soup = BeautifulSoup(html, "html.parser")
    info = soup.select_one(".qt_info_mid")
    if not info:
        raise ValueError("qt_info_mid not found")
    page_date = info.select_one("p.date").get_text(strip=True)  # 2026.10.18(일)
    m = re.match(r"(\d{4})\.(\d{2})\.(\d{2})", page_date)
    if not m or "-".join(m.groups()) != date:
        raise ValueError(f"page date {page_date!r} != requested {date}")
    title = info.select_one("p.sbj").get_text(strip=True)
    words = [p.get_text(strip=True) for p in info.select("p.word")]
    passage = verse_ref = ""
    for w in words:
        if w.startswith("오늘의 본문"):
            passage = w.split(":", 1)[1].strip()
        elif w.startswith("오늘의 한 구절"):
            verse_ref = w.split(":", 1)[1].strip()

    sections = {}
    for sec in soup.select(".qt_cont .qt_cont_sec"):
        tit = sec.select_one("h4.tit")
        cont = sec.select_one(".cont")
        if tit and cont:
            sections[tit.get_text(strip=True)] = _text(cont)

    verse = sections.get("오늘의 한 구절", "")
    krv = new = ""
    mm = re.search(r"\[개역개정\]\s*(.*?)\s*\[새번역\]\s*(.*)", verse, re.S)
    if mm:
        krv, new = mm.group(1).strip(), mm.group(2).strip()
    else:
        krv = verse

    questions = [q.strip() for q in re.split(r"\n\s*\n", sections.get("묵상질문", "")) if q.strip()]
    qt = {
        "date": date,
        "title": title,
        "passage": passage,
        "verseRef": verse_ref,
        "verseKrv": krv,
        "verseNew": new,
        "summary": sections.get("본문 개요", ""),
        "meditation": sections.get("한 구절 묵상", ""),
        "questions": questions,
        "prayer": sections.get("심정이 통하는 기도", ""),
        "sourceUrl": f"{BASE}?ov_date={date}",
    }
    for k in ("title", "passage", "verseRef", "summary", "meditation"):
        if not qt[k]:
            raise ValueError(f"required field empty: {k}")
    return qt


def firestore_client():
    import firebase_admin
    from firebase_admin import credentials, firestore

    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        sys.exit("FIREBASE_SERVICE_ACCOUNT 환경변수가 없습니다 (--dry-run 으로 파싱만 확인 가능)")
    firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
    return firestore.client()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--backfill", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    end = datetime.strptime(a.date or today_kst(), "%Y-%m-%d")
    dates = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(max(a.backfill, 1))]

    db = None if a.dry_run else firestore_client()
    failed = 0
    for d in dates:
        try:
            qt = parse(fetch_html(d), d)
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {d}: {e}", file=sys.stderr)
            failed += 1
            if a.backfill:
                time.sleep(1)
                continue
            sys.exit(1)
        if a.dry_run:
            print(json.dumps(qt, ensure_ascii=False, indent=2))
        else:
            from firebase_admin import firestore

            qt["fetchedAt"] = firestore.SERVER_TIMESTAMP
            db.collection("qt").document(d).set(qt, merge=True)
            print(f"[OK] {d} {qt['title']}")
        if len(dates) > 1:
            time.sleep(1.5)  # 사이트에 부담 주지 않기
    if failed and failed == len(dates):
        sys.exit(1)


if __name__ == "__main__":
    main()
