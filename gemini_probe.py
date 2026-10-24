"""진단용: 어떤 Gemini 모델이 지금 YouTube 영상을 처리하는지 측정한다 (키 값은 출력하지 않는다)."""
import os
import time

from google import genai
from google.genai import errors, types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                      http_options=types.HttpOptions(timeout=120_000))  # 호출당 최대 120초

VIDEOS = {
    "이전 설교(요약 성공했던 영상)": "https://www.youtube.com/watch?v=gaQyrKtJaPM",
    "오늘 설교(403 났던 영상)": "https://www.youtube.com/watch?v=F96rB2olAao",
}


def models():
    names = []
    for m in client.models.list():
        acts = getattr(m, "supported_actions", None) or []
        n = m.name.replace("models/", "")
        if "generateContent" in acts and "flash" in n and "image" not in n and "tts" not in n:
            names.append(n)
    return sorted(set(names))


def call(model, parts):
    t = time.time()
    try:
        r = client.models.generate_content(model=model, contents=types.Content(parts=parts))
        return f"OK {time.time() - t:.0f}s: {(r.text or '')[:40]!r}"
    except errors.APIError as e:
        return f"{e.code} {time.time() - t:.0f}s: {str(e.message)[:80]}"
    except Exception as e:  # 시간 초과 등
        return f"{type(e).__name__} {time.time() - t:.0f}s"


names = models()
print("사용 가능한 flash 모델:", names, flush=True)
for n in names:
    print(f"\n== {n}", flush=True)
    print("  텍스트:", call(n, [types.Part(text="한 단어로 답해: 안녕")]), flush=True)
    for label, url in VIDEOS.items():
        print(f"  {label}:", call(n, [types.Part(file_data=types.FileData(file_uri=url)),
                                      types.Part(text="이 영상의 설교 제목만 한 줄로 답해.")]), flush=True)
