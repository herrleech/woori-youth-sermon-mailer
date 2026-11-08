"""분당우리교회 유튜브 채널(청년교구 + 본채널)에 새 설교가 올라오면 요약해서 설교마다 이메일로 보낸다."""
import html
import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import feedparser
import requests

CHANNELS = [
    # library=True 인 채널만 library/, 대시보드, 앱(Firestore)에 저장한다
    {"id": "UCJe7PaggYL8ArlQPvvJbN3Q", "name": "청년교구", "footer": "분당우리교회 청년교구",
     "audience": "청년들", "library": True},  # @woori_youth
    {"id": "UCBh3Qv-rKu6ZDxEcrio70Hw", "name": "분당우리교회", "footer": "분당우리교회",
     "audience": "성도들", "library": True},  # @BundangWooriChurch (과거분 백필은 청년교구만)
]
YOUTH = CHANNELS[0]
EXCLUDE_KEYWORDS = ("새벽기도회",)  # 제목에 포함되면 메일을 보내지 않는다 (필요하면 여기에 추가)
LIVE_PATTERN =re.compile(r"생방송|라이브|🔴|\blive\b", re.I)  # 방송 중인 영상은 요약할 수 없다
SEEN_FILE = Path(__file__).with_name("seen.json")
LIBRARY_DIR = Path(__file__).with_name("library")
SERMON_KEYWORDS = ("목사", "전도사", "강도사")  # 찬양 영상 등은 제외
GIVE_UP_AFTER = timedelta(days=2)  # 요약이 계속 실패하면 이 시간 후 간단 안내만 보낸다
# 새 설교 메일은 조금 끈질기게(영상당 최대 약 2분 x 모델 수), 백필은 한 번만 시도하고 다음 날 다시 한다
RETRY_WAITS = (0,) if os.environ.get("BACKFILL_ONLY") == "1" else (0, 10)
CALL_TIMEOUT_MS = 90_000  # Gemini 호출 한 번당 최대 90초
MAX_AGE = timedelta(days=3)  # 이보다 오래된 영상은 보내지 않고 기록만 한다
# 2026-10-24 측정(gemini_probe.py): 3.6/3.5/3.1-lite가 두 영상 모두 10~50초에 성공, 3.8/latest는 503·504가 잦았다.
# 모델 상황은 바뀌므로 문제가 생기면 Actions에서 gemini-probe를 다시 돌려 순서를 정한다.
GEMINI_MODELS = [m for m in (os.environ.get("GEMINI_MODEL"), "gemini-3.6-flash", "gemini-3.5-flash",
                             "gemini-3.1-flash-lite") if m]
DRY_RUN = os.environ.get("DRY_RUN") == "1"

PROMPT = """다음은 {channel} 설교 영상입니다. 영상을 듣고 아래 JSON 객체 하나로만 답하세요 (목록이 아니라 객체).
- title: 설교 제목 (영상 제목에서 날짜/교회명/부서명을 뺀 설교 제목)
- scripture: 본문 성경구절 (예: 열왕기상 12장 25-33절). 모르면 "확인되지 않음"
- preacher: 설교자 (예: 지원일 목사)
- key_message: 설교의 핵심 메시지 한 문장 (60자 이내)
- points: 설교의 흐름을 3~5개 요점으로 나눈 객체 배열. 각 객체는 heading(요점 소제목, 20자 이내)과 body를 가진다.
  body는 반드시 3문장 이상(3~5문장)으로 쓴다. 설교자가 이 요점에서 실제로 말한 내용(인용한 성경 구절, 든 예화, 주장의 근거와 논리의 흐름)을 구체적으로 담아, 설교를 듣지 못한 사람도 맥락과 내용을 이해할 수 있게 한다. "~해야 합니다" 같은 일반론만 나열하지 않는다.
- takeaways: {audience}이 삶에 적용할 점 2~3개 (문자열 배열)
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


def uploads_playlist(ch):
    return f"UU{ch['id'][2:]}"  # 채널 ID(UC...)에서 업로드 목록 ID(UU...)를 만든다


def video(vid, title, published, description, ch):
    return {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "title": html.unescape(title),
            "published": datetime.fromisoformat(published.replace("Z", "+00:00")), "description": description,
            "channel": ch}


def api_items(key, ch, page_size=20, token=None):
    params = {"part": "snippet,contentDetails", "playlistId": uploads_playlist(ch),
              "maxResults": page_size, "key": key}
    if token:
        params["pageToken"] = token
    r = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    items = [video(i["contentDetails"]["videoId"], i["snippet"]["title"],
                   i["contentDetails"].get("videoPublishedAt") or i["snippet"]["publishedAt"],
                   i["snippet"].get("description", ""), ch)
             for i in data["items"]]
    return items, data.get("nextPageToken")


def fetch_via_api(key, ch):
    """YouTube Data API(공식). 클라우드 서버에서도 안정적으로 동작한다."""
    return api_items(key, ch, page_size=30)[0]


def fetch_all_via_api(key, ch=YOUTH, max_items=300):
    """업로드 목록 전체(최신순)를 페이지 단위로 가져온다."""
    out, token = [], None
    while len(out) < max_items:
        items, token = api_items(key, ch, page_size=50, token=token)
        out += items
        if not token:
            break
    return out


def library_path(v):
    return LIBRARY_DIR / f"{v['published'].strftime('%Y-%m-%d')}_{v['id']}.json"


def library_record(v, info):
    return {
        "video_id": v["id"], "url": v["url"], "published": v["published"].isoformat(),
        "video_title": v["title"], "title": info.get("title", ""), "scripture": info.get("scripture", ""),
        "preacher": info.get("preacher", ""), "summary": info.get("summary", ""),
        "key_message": info.get("key_message", ""), "points": info.get("points", []),
        "takeaways": info.get("takeaways", []), "tags": info.get("tags", []),
        "thumbnail": f"https://i.ytimg.com/vi/{v['id']}/hqdefault.jpg", "channel": v["channel"]["name"],
    }


_firestore = None


def firestore_db():
    """Firebase 서비스 계정이 설정돼 있으면 Firestore 클라이언트를, 없으면 None을 돌려준다."""
    global _firestore
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if _firestore is None and raw:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
        _firestore = firestore.client()
    return _firestore


def save_to_firestore(record):
    """앱이 읽는 sermons/{영상ID} 문서로 저장한다. 실패해도 메일 발송은 계속한다 (library/*.json 이 원본)."""
    try:
        db = firestore_db()
        if db is None:
            return
        from firebase_admin import firestore

        db.collection("sermons").document(record["video_id"]).set({**record, "updatedAt": firestore.SERVER_TIMESTAMP})
        print(f"Firestore 저장 완료: {record['video_id']}")
    except Exception as e:
        print(f"Firestore 저장 실패(메일은 계속 진행): {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)


def push_new_sermon(v, info):
    """새 설교를 앱 알림으로도 알린다 (알림을 켜둔 기기에만). 실패해도 메일 발송은 계속한다."""
    if DRY_RUN or not v["channel"]["library"]:
        return
    try:
        db = firestore_db()
        if db is None:
            return
        import push

        body = " · ".join(x for x in (info.get("scripture"), info.get("preacher")) if x)
        if info.get("key_message"):
            body += "\n" + info["key_message"]
        sent, failed, removed = push.send(db, "newSermon", f"[{v['channel']['name']}] {info.get('title') or v['title']}",
                                          body, f"#/sermon/{v['id']}", tag=v["id"])
        print(f"푸시 알림: 성공 {sent}, 실패 {failed}, 만료 정리 {removed}")
    except Exception as e:
        print(f"푸시 알림 실패(메일은 계속 진행): {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)


def save_library(v, info):
    """설교 하나당 JSON 파일 하나로 저장하고(대시보드 데이터), 앱용 Firestore에도 저장한다."""
    if DRY_RUN or not v["channel"]["library"]:
        return
    LIBRARY_DIR.mkdir(exist_ok=True)
    record = library_record(v, info)
    library_path(v).write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    save_to_firestore(record)


def fetch_via_rss(ch):
    """RSS는 가끔 404/500을 내고 클라우드 IP는 막히기도 해서 여러 번 시도한다."""
    urls = [f"https://www.youtube.com/feeds/videos.xml?channel_id={ch['id']}",
            f"https://www.youtube.com/feeds/videos.xml?playlist_id={uploads_playlist(ch)}"]
    for attempt in range(8):
        try:
            r = requests.get(urls[attempt % 2], headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            r.raise_for_status()
            entries = feedparser.parse(r.content).entries
            if entries:
                return [video(e.yt_videoid, e.title, e.published, e.get("summary", ""), ch) for e in entries]
        except requests.RequestException as e:
            print(f"피드 재시도 {attempt + 1}: {e}", file=sys.stderr)
        time.sleep(4 * (attempt + 1))
    return None


def fetch_videos():
    """모든 채널의 최신 영상 목록. 가져온 채널이 하나도 없으면 None."""
    key = os.environ.get("YOUTUBE_API_KEY")
    out, ok = [], 0
    for ch in CHANNELS:
        items = None
        if key:
            try:
                items = fetch_via_api(key, ch)
            except (requests.RequestException, KeyError) as e:
                print(f"[{ch['name']}] YouTube API 실패: {type(e).__name__}", file=sys.stderr)
        if items is None:
            items = fetch_via_rss(ch)
        if items is None:
            print(f"[{ch['name']}] 영상 목록을 가져오지 못했습니다. 다음 실행에서 다시 시도합니다.", file=sys.stderr)
            continue
        ok += 1
        out += items
    return out if ok else None


def is_sermon(title):
    return (any(k in title for k in SERMON_KEYWORDS) and not LIVE_PATTERN.search(title)
            and not any(k in title for k in EXCLUDE_KEYWORDS))


def as_info(data):
    """Gemini가 객체 대신 [객체] 목록을 돌려주는 일이 있어 정리한다. 형식이 이상하면 예외 -> 다른 모델로 재시도."""
    if isinstance(data, list):
        data = next((x for x in data if isinstance(x, dict)), None)
    if not isinstance(data, dict):
        raise ValueError("예상하지 못한 응답 형식")
    raw = data.get("points") if isinstance(data.get("points"), list) else []
    data["points"] = [{"heading": str(p.get("heading", "")).strip(), "body": str(p["body"]).strip()}
                      for p in raw if isinstance(p, dict) and p.get("body")]
    data["key_message"] = str(data.get("key_message") or "").strip()
    if data["points"]:  # 요약 문자열은 코드가 직접 만든다 (모델이 줄바꿈을 빼먹어도 읽기 좋게)
        blocks = [data["key_message"]] if data["key_message"] else []
        blocks += [f"{i}. {p['heading']}\n{p['body']}" if p["heading"] else f"{i}. {p['body']}"
                   for i, p in enumerate(data["points"], 1)]
        data["summary"] = "\n\n".join(blocks)
    for k in ("takeaways", "tags"):  # 문자열 배열이어야 한다
        if not isinstance(data.get(k), list):
            data[k] = []
    if not data["points"]:
        if not data.get("summary"):
            raise ValueError("요약 내용이 없는 응답")
        raise NoPoints(data)  # 내용은 있지만 소제목 형식이 아님 -> 다른 모델을 먼저 시도하고, 안 되면 이 결과를 쓴다
    return data


class NoPoints(ValueError):
    """요약은 있으나 points(소제목+본문) 구조가 빠진 응답. args[0] 에 정리된 결과가 들어 있다."""


def generate_json(contents):
    """후보 모델을 순서대로 시도한다 (모델이 단종/변경돼도 동작하도록)."""
    from google import genai
    from google.genai import errors, types

    # 호출 하나가 몇 분씩 매달리지 않도록 시간 제한을 둔다 (혼잡한 모델은 503을 내기까지 오래 걸린다)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                          http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS))
    last = unstructured = None
    for model in GEMINI_MODELS:
        for attempt, wait in enumerate(RETRY_WAITS):  # 서버 오류/시간 초과는 잠시 뒤 한 번 더
            time.sleep(wait)
            try:
                resp = client.models.generate_content(
                    model=model, contents=contents,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                return as_info(json.loads(resp.text))
            except NoPoints as e:  # 소제목 없는 요약: 일단 보관해두고 다음 모델로 (형식을 지키는 모델을 찾는다)
                print(f"모델 {model}: 소제목 형식이 아닌 응답, 다음 모델 시도", file=sys.stderr)
                unstructured = unstructured or e.args[0]
                last = e
                break
            except errors.ClientError as e:  # 모델 없음/한도 초과/영상 거부 등은 모델마다 다를 수 있어 다음 모델로
                print(f"모델 {model} 사용 불가({e.code}), 다음 모델 시도", file=sys.stderr)
                last = e
                break
            except Exception as e:  # 503/504, 시간 초과, 응답 형식 오류
                print(f"모델 {model} 실패({type(e).__name__}), 시도 {attempt + 1}", file=sys.stderr)
                last = e
    if unstructured:  # 어떤 모델도 소제목 형식을 못 지켰으면, 요약 없이 실패하는 것보다 이 결과를 쓴다
        print("소제목 형식을 지킨 응답이 없어 일반 요약을 사용합니다", file=sys.stderr)
        return unstructured
    raise last


def prompt_for(ch, title, description):
    return PROMPT.format(channel=ch["footer"], audience=ch["audience"], title=title, description=description)


def summarize_with_video(url, ch, title, description):
    from google.genai import types

    return generate_json(types.Content(parts=[
        types.Part(file_data=types.FileData(file_uri=url)),
        types.Part(text=prompt_for(ch, title, description)),
    ]))


def summarize_with_transcript(video_id, ch, title, description):
    from youtube_transcript_api import YouTubeTranscriptApi

    transcript = " ".join(t.text for t in YouTubeTranscriptApi().fetch(video_id, languages=["ko"]))
    return generate_json(prompt_for(ch, title, description) + "\n\n[설교 자막]\n" + transcript)


def summarize(video_id, url, ch, title, description):
    for name, fn in (
        ("영상 직접 분석", lambda: summarize_with_video(url, ch, title, description)),
        ("자막 분석", lambda: summarize_with_transcript(video_id, ch, title, description)),
    ):
        try:
            return fn()
        except Exception as e:  # 한 방식이 실패하면 다음 방식으로
            print(f"[{video_id}] {name} 실패: {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
    return None


def render_email(info, url, published, ch):
    esc = html.escape
    h3 = "margin:28px 0 10px;font-size:17px;color:#1f3d34"
    takeaways = "".join(f'<li style="margin:0 0 8px">{esc(t)}</li>' for t in info.get("takeaways", []))
    if info.get("points"):  # 핵심 메시지 상자 + 요점마다 소제목/본문 (문단 사이를 넉넉히 띄운다)
        key = info.get("key_message", "")
        summary_html = (f'<div style="background:#eef4f1;border-left:4px solid #2f5d50;padding:14px 16px;'
                        f'margin:0 0 8px;font-size:16px;font-weight:bold">{esc(key)}</div>' if key else "")
        summary_html += "".join(
            f'<h4 style="margin:22px 0 6px;font-size:16px">{i}. {esc(p["heading"])}</h4>'
            f'<p style="margin:0">{esc(p["body"])}</p>' if p["heading"] else
            f'<p style="margin:14px 0 0">{i}. {esc(p["body"])}</p>'
            for i, p in enumerate(info["points"], 1))
    else:  # 요점 구조가 없는 요약(요약 실패 안내 등)은 빈 줄 기준으로 문단을 나눈다
        paras = [p.strip() for p in info.get("summary", "").split("\n\n") if p.strip()]
        summary_html = "".join(f'<p style="margin:0 0 14px">{esc(p).replace(chr(10), "<br>")}</p>' for p in paras)
    body = f"""
<div style="font-family:'Malgun Gothic',sans-serif;max-width:640px;margin:auto;padding:16px 18px;line-height:1.85;font-size:15px;color:#222;background:#ffffff">
  <h2 style="margin:0 0 6px;font-size:22px;line-height:1.4">{esc(info.get('title', ''))}</h2>
  <p style="margin:0;color:#555">📖 {esc(info.get('scripture', ''))} &nbsp;|&nbsp; 🎤 {esc(info.get('preacher', ''))}</p>
  <p style="margin:4px 0 16px;color:#888;font-size:13px">{published}</p>
  <p style="margin:0"><a href="{url}" style="background:#c00;color:#fff;padding:9px 16px;text-decoration:none;border-radius:4px;display:inline-block">▶ 영상 보기</a></p>
  <h3 style="{h3}">설교 요약</h3>{summary_html}
  {f'<h3 style="{h3}">적용 포인트</h3><ul style="margin:0;padding-left:22px">{takeaways}</ul>' if takeaways else ''}
  <hr style="margin:32px 0 12px;border:0;border-top:1px solid #ddd"><p style="color:#999;font-size:12px;margin:0">{ch['footer']} 유튜브 새 설교 자동 알림 (AI 요약이라 부정확할 수 있어요)</p>
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


def send_test(video_id):
    """TEST_VIDEO=영상ID : 그 영상 하나만 요약해 메일을 보낸다. '보낸 영상' 기록과 라이브러리는 건드리지 않는다."""
    videos = fetch_videos() or []
    v = next((x for x in videos if x["id"] == video_id), None)
    if v is None:
        print(f"테스트 영상 {video_id} 을(를) 최근 영상 목록에서 찾지 못했습니다.", file=sys.stderr)
        sys.exit(1)
    ch = v["channel"]
    info = summarize(v["id"], v["url"], ch, v["title"], v["description"])
    if info is None:
        print(f"테스트 영상 요약 실패: {v['title']}", file=sys.stderr)
        sys.exit(1)
    kst = timezone(timedelta(hours=9))
    body_html, body_text = render_email(info, v["url"], v["published"].astimezone(kst).strftime("%Y-%m-%d %H:%M"), ch)
    send_mail(f"[테스트] [{ch['name']} 새 설교] {info.get('title', v['title'])}", body_html, body_text)
    print(f"테스트 발송 완료: {v['title']}")


def add_to_library(ids):
    """LIBRARY_VIDEOS=id1,id2 : 메일은 보내지 않고 그 영상들을 요약해 라이브러리/앱에만 저장한다.
    (이미 메일이 나갔거나 과거에 기록만 한 설교를 보충할 때 쓴다. 최근 영상 목록에 있는 것만 가능)"""
    videos = {v["id"]: v for v in (fetch_videos() or [])}
    bad = 0
    for vid in ids:
        v = videos.get(vid)
        info = v and summarize(vid, v["url"], v["channel"], v["title"], v["description"])
        if not info:
            print(f"라이브러리 추가 실패: {vid} ({'목록에 없음' if not v else '요약 실패'})", file=sys.stderr)
            bad += 1
            continue
        save_library(v, info)
        print(f"라이브러리 추가: {v['title']}")
    if bad:
        sys.exit(1)


def main():
    if os.environ.get("LIBRARY_VIDEOS", "").strip():
        add_to_library([x.strip() for x in os.environ["LIBRARY_VIDEOS"].split(",") if x.strip()])
        return
    if os.environ.get("TEST_VIDEO", "").strip():
        send_test(os.environ["TEST_VIDEO"].strip())
        return
    if os.environ.get("BACKFILL_ONLY") == "1":
        backfill()
        return
    videos = fetch_videos()
    if videos is None:  # 일시적 장애: 실패로 처리하지 않고 다음 실행에 재시도
        print("유튜브 영상 목록을 가져오지 못했습니다. 다음 실행에서 다시 시도합니다.", file=sys.stderr)
        return
    seen = load_seen()

    if seen is None:  # 첫 실행: 과거 영상은 보내지 않고 기록만 한다
        save_seen({v["id"] for v in videos})
        print(f"첫 실행: 기존 영상 {len(videos)}개를 기록만 했습니다.")
        return
    seen = set(seen)

    for ch in CHANNELS:  # 새로 추가한 채널의 첫 확인: 과거 영상은 보내지 않고 기록만 한다
        ids = {v["id"] for v in videos if v["channel"] is ch}
        if ids and not ids & seen:
            seen |= ids
            print(f"[{ch['name']}] 새 채널 첫 확인: 기존 영상 {len(ids)}개를 기록만 했습니다.")
            if not DRY_RUN:
                save_seen(seen)

    now = datetime.now(timezone.utc)
    kst = timezone(timedelta(hours=9))
    pending = sorted((v for v in videos if v["id"] not in seen), key=lambda v: v["published"])  # 오래된 것부터
    for v in pending:
        vid, url, title, published, ch = v["id"], v["url"], v["title"], v["published"], v["channel"]
        if not is_sermon(title) or now - published > MAX_AGE:
            print(f"설교가 아니거나 오래된 영상, 기록만 함: {title}")
            seen.add(vid)
            continue
        info = summarize(vid, url, ch, title, v["description"])
        if info is None:
            if now - published < GIVE_UP_AFTER:
                print(f"요약 실패, 다음 실행에서 재시도: {title}")
                continue
            info = {"title": title, "scripture": "-", "preacher": "-",
                    "summary": "요약을 만들지 못했습니다. 영상 링크에서 확인해주세요.", "takeaways": []}
        else:
            save_library(v, info)
            push_new_sermon(v, info)
        body_html, body_text = render_email(info, url, published.astimezone(kst).strftime("%Y-%m-%d %H:%M"), ch)
        send_mail(f"[{ch['name']} 새 설교] {info.get('title', title)}", body_html, body_text)
        print(f"발송 완료: {title}")
        seen.add(vid)
        if not DRY_RUN:
            save_seen(seen)  # 실행이 중간에 취소돼도 이미 보낸 메일이 다시 가지 않도록 바로 기록

    if not DRY_RUN:
        save_seen(seen)
    backfill()


def backfill():
    """부가 작업이라 오류가 나도 실행 전체를 실패로 만들지 않는다 (실패 알림 메일 방지)."""
    try:
        _backfill()
    except Exception as e:
        print(f"백필 오류(무시하고 다음에 다시 시도): {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)


def _backfill():
    """BACKFILL=N 이면 라이브러리에 없는 지난 설교를 최대 N편 요약해 저장한다 (메일은 보내지 않음)."""
    limit = int(os.environ.get("BACKFILL", "0"))
    key = os.environ.get("YOUTUBE_API_KEY")
    if limit <= 0 or not key:
        return
    done = fails = 0
    for v in fetch_all_via_api(key, YOUTH):  # 최신순 (라이브러리는 청년교구만)
        if done >= limit:
            break
        if not is_sermon(v["title"]) or library_path(v).exists():
            continue
        info = summarize(v["id"], v["url"], YOUTH, v["title"], v["description"])
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
