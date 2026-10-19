"""분당우리교회 청년교구 유튜브 채널에 새 설교가 올라오면 요약해서 이메일로 보낸다."""
import html
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
import requests

CHANNEL_ID = "UCJe7PaggYL8ArlQPvvJbN3Q"  # @woori_youth
FEED_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
UPLOADS_FEED_URL = f"https://www.youtube.com/feeds/videos.xml?playlist_id=UU{CHANNEL_ID[2:]}"
SEEN_FILE = Path(__file__).with_name("seen.json")
LIBRARY_DIR = Path(__file__).with_name("library")
SERMON_KEYWORDS = ("목사", "전도사", "강도사")  # 찬양 영상 등은 제외
GIVE_UP_AFTER = timedelta(days=2)  # 요약이 계속 실패하면 이 시간 후 간단 안내만 보낸다
MAX_AGE = timedelta(days=3)  # 이보다 오래된 영상은 보내지 않고 기록만 한다
GEMINI_MODELS = [m for m in (os.environ.get("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-flash-latest") if m]
DRY_RUN = os.environ.get("DRY_RUN") == "1"

PROMPT = """다음은 교회 청년부 설교 영상입니다. 영상을 듣고 아래 JSON으로만 답하세요.
- title: 설교 제목 (영상 제목에서 날짜/교회명/부서명을 뺀 설교 제목)
- scripture: 본문 성경구절 (예: 열왕기상 12장 25-33절). 모르면 "확인되지 않음"
- preacher: 설교자 (예: 지원일 목사)
- summary: 설교 내용을 한국어로 정리한 글. 핵심 메시지 한 줄 + 3~5개 소제목별 요점 (총 400~700자)
- takeaways: 청년들이 삶에 적용할 점 2~3개 (문자열 배열)
- tags: 설교의 주제 태그 2~4개 (짧은 한국어 명사, 문자열 배열. 예: 불안, 관계, 전도, 순종)

영상 제목: {title}
영상 설명:
{description}
"""


def load_seen():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8-sig"))
    return None


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=1), encoding="utf-8")


def video(vid, title, published, description):
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": html.unescape(title),
            "published": datetime.fromisoformat(published.replace("Z", "+00:00")), "description": description}


def fetch_via_api(key):
    """YouTube Data API(공식). 클라우드 서버에서도 안정적으로 동작한다."""
    r = requests.get(
        "https://www.googleapis.com/youtube/v3/playlistItems",
        params={"part": "snippet,contentDetails", "playlistId": f"UU{CHANNEL_ID[2:]}",
                "maxResults": 20, "key": key},
        timeout=30,
    )
    r.raise_for_status()
    return [video(i["contentDetails"]["videoId"], i["snippet"]["title"],
                  i["contentDetails"].get("videoPublishedAt") or i["snippet"]["publishedAt"],
                  i["snippet"].get("description", ""))
            for i in r.json()["items"]]


def fetch_all_via_api(key, max_items=300):
    """업로드 목록 전체(최신순)를 페이지 단위로 가져온다."""
    out, token = [], None
    while len(out) < max_items:
        params = {"part": "snippet,contentDetails", "playlistId": f"UU{CHANNEL_ID[2:]}",
                  "maxResults": 50, "key": key}
        if token:
            params["pageToken"] = token
        r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out += [video(i["contentDetails"]["videoId"], i["snippet"]["title"],
                      i["contentDetails"].get("videoPublishedAt") or i["snippet"]["publishedAt"],
                      i["snippet"].get("description", "")) for i in data["items"]]
        token = data.get("nextPageToken")
        if not token:
            break
    return out


def library_path(v):
    return LIBRARY_DIR / f"{v['published'].strftime('%Y-%m-%d')}_{v['id']}.json"


def save_library(v, info):
    """설교 하나당 JSON 파일 하나로 저장한다 (나중에 대시보드의 데이터가 된다)."""
    if DRY_RUN:
        return
    LIBRARY_DIR.mkdir(exist_ok=True)
    record = {
        "video_id": v["id"], "url": v["url"], "published": v["published"].isoformat(),
        "video_title": v["title"], "title": info.get("title", ""), "scripture": info.get("scripture", ""),
        "preacher": info.get("preacher", ""), "summary": info.get("summary", ""),
        "takeaways": info.get("takeaways", []), "tags": info.get("tags", []),
        "thumbnail": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg",
    }
    library_path(v).write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_via_rss():
    """RSS는 가끔 404/500을 내고 클라우드 IP는 막히기도 해서 여러 번 시도한다."""
    urls = [FEED_URL, UPLOADS_FEED_URL]
    for attempt in range(8):
        try:
            r = requests.get(urls[attempt % 2], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            entries = feedparser.parse(r.content).entries
            if entries:
                return [video(e.yt_videoid, e.title, e.published, e.get("summary", "")) for e in entries]
        except requests.RequestException as e:
            print(f"피드 재시도 {attempt + 1}: {e}", file=sys.stderr)
        time.sleep(4 * (attempt + 1))
    return None


def fetch_videos():
    """최신순 영상 목록. 실패하면 None."""
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        try:
            return fetch_via_api(key)
        except (requests.RequestException, KeyError) as e:
            print(f"YouTube API 실패: {type(e).__name__}", file=sys.stderr)
    return fetch_via_rss()


def is_sermon(title):
    return any(k in title for k in SERMON_KEYWORDS)


def generate_json(contents):
    """후보 모델을 순서대로 시도한다 (모델이 단종/변경돼도 동작하도록)."""
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    last = None
    for model in GEMINI_MODELS:
        for attempt, wait in enumerate((0, 30, 90, 180)):  # 503(서버 혼잡)은 잠시 뒤 다시 시도
            time.sleep(wait)
            try:
                resp = client.models.generate_content(
                    model=model, contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return json.loads(resp.text)
            except errors.ServerError as e:
                print(f"모델 {model} 서버 오류({e.code}), 재시도 {attempt + 1}", file=sys.stderr)
                last = e
            except errors.ClientError as e:
                if e.code not in (404, 429):  # 모델 없음/한도 초과일 때만 다음 모델로
                    raise
                print(f"모델 {model} 사용 불가({e.code}), 다음 모델 시도", file=sys.stderr)
                last = e
                break
    raise last


def summarize_with_video(url, title, description):
    from google.genai import types

    return generate_json(types.Content(parts=[
        types.Part(file_data=types.FileData(file_uri=url)),
        types.Part(text=PROMPT.format(title=title, description=description)),
    ]))


def summarize_with_transcript(video_id, title, description):
    from youtube_transcript_api import YouTubeTranscriptApi

    transcript = " ".join(t.text for t in YouTubeTranscriptApi().fetch(video_id, languages=["ko"]))
    return generate_json(PROMPT.format(title=title, description=description) + "\n\n[설교 자막]\n" + transcript)


def summarize(video_id, url, title, description):
    for name, fn in (
        ("영상 직접 분석", lambda: summarize_with_video(url, title, description)),
        ("자막 분석", lambda: summarize_with_transcript(video_id, title, description)),
    ):
        try:
            return fn()
        except Exception as e:  # 한 방식이 실패하면 다음 방식으로
            print(f"[{video_id}] {name} 실패: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
    return None


def render_email(info, url, published):
    takeaways = "".join(f"<li>{html.escape(t)}</li>" for t in info.get("takeaways", []))
    summary = html.escape(info.get("summary", "")).replace("\n", "<br>")
    body = f"""
<div style="font-family:'Malgun Gothic',sans-serif;max-width:640px;margin:auto;line-height:1.7;color:#222">
  <h2 style="margin-bottom:4px">{html.escape(info.get('title', ''))}</h2>
  <p style="margin:0;color:#555">📖 {html.escape(info.get('scripture', ''))} &nbsp;|&nbsp; 🎤 {html.escape(info.get('preacher', ''))}</p>
  <p style="margin:4px 0 16px;color:#888;font-size:13px">{published}</p>
  <p><a href="{url}" style="background:#c00;color:#fff;padding:8px 14px;text-decoration:none;border-radius:4px">▶ 영상 보기</a></p>
  <h3>설교 요약</h3><p>{summary}</p>
  {'<h3>적용 포인트</h3><ul>' + takeaways + '</ul>' if takeaways else ''}
  <hr><p style="color:#999;font-size:12px">분당우리교회 청년교구 유튜브 새 설교 자동 알림 (AI 요약이라 부정확할 수 있어요)</p>
</div>"""
    text = (f"{info.get('title', '')}\n본문: {info.get('scripture', '')}\n설교자: {info.get('preacher', '')}\n"
            f"{url}\n\n{info.get('summary', '')}\n")
    return body, text


def send_mail(subject, body_html, body_text):
    if DRY_RUN:
        print("=== DRY RUN (메일 발송 안 함) ===\n제목:", subject, "\n", body_text)
        return
    user, pw = os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"]
    to = [a.strip() for a in os.environ["MAIL_TO"].split(",") if a.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to)
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.sendmail(user, to, msg.as_string())


def main():
    if os.environ.get("BACKFILL_ONLY") == "1":
        backfill()
        return
    videos = fetch_videos()
    if videos is None:  # 일시적 장애: 실패로 처리하지 않고 다음 실행(30분 뒤)에 재시도
        print("유튜브 영상 목록을 가져오지 못했습니다. 다음 실행에서 다시 시도합니다.", file=sys.stderr)
        return
    seen = load_seen()

    if seen is None:  # 첫 실행: 과거 영상은 보내지 않고 기록만 한다
        save_seen({v["id"] for v in videos})
        print(f"첫 실행: 기존 영상 {len(videos)}개를 기록만 했습니다.")
        return
    seen = set(seen)

    now = datetime.now(timezone.utc)
    kst = timezone(timedelta(hours=9))
    for v in [v for v in reversed(videos) if v["id"] not in seen]:
        vid, url, title, published = v["id"], v["url"], v["title"], v["published"]
        if not is_sermon(title) or now - published > MAX_AGE:
            print(f"설교가 아니거나 오래된 영상, 기록만 함: {title}")
            seen.add(vid)
            continue
        info = summarize(vid, url, title, v["description"])
        if info is None:
            if now - published < GIVE_UP_AFTER:
                print(f"요약 실패, 다음 실행에서 재시도: {title}")
                continue
            info = {"title": title, "scripture": "-", "preacher": "-",
                    "summary": "요약을 만들지 못했습니다. 영상 링크에서 확인해주세요.", "takeaways": []}
        else:
            save_library(v, info)
        body_html, body_text = render_email(info, url, published.astimezone(kst).strftime("%Y-%m-%d %H:%M"))
        send_mail(f"[청년교구 새 설교] {info.get('title', title)}", body_html, body_text)
        print(f"발송 완료: {title}")
        seen.add(vid)

    if not DRY_RUN:
        save_seen(seen)
    backfill()


def backfill():
    """BACKFILL=N 이면 라이브러리에 없는 지난 설교를 최대 N편 요약해 저장한다 (메일은 보내지 않음)."""
    limit = int(os.environ.get("BACKFILL", "0"))
    key = os.environ.get("YOUTUBE_API_KEY")
    if limit <= 0 or not key:
        return
    done = fails = 0
    for v in fetch_all_via_api(key):  # 최신순
        if done >= limit:
            break
        if not is_sermon(v["title"]) or library_path(v).exists():
            continue
        info = summarize(v["id"], v["url"], v["title"], v["description"])
        if info is None:
            fails += 1
            print(f"백필 실패: {v['title']}", file=sys.stderr)
            if fails >= 2:  # 무료 한도 초과/서버 혼잡일 가능성이 커서 오늘은 멈춘다
                print("연속 실패로 오늘 백필을 중단합니다.", file=sys.stderr)
                break
            continue
        fails = 0
        time.sleep(20)  # 분당 요청 한도 보호
        save_library(v, info)
        print(f"백필 저장: {v['title']}")
        done += 1


if __name__ == "__main__":
    main()
