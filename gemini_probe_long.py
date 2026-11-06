"""진단용: 본채널의 긴 설교 영상이 실제 파이프라인(모델 순서, 90초 제한)에서 요약되는지 측정한다."""
import os
import time

from google import genai
from google.genai import types

import sermon_mailer as m

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
CH = m.CHANNELS[1]
VIDEOS = {
    "oZUyyd7wBaw": "금요기도회",
    "-Ma0LnJpTO4": "새벽기도회",
    "cWI2HCo9wH8": "주일설교(이찬수)",
}

for vid, label in VIDEOS.items():
    url = f"https://www.youtube.com/watch?v={vid}"
    print(f"\n== {label} {url}", flush=True)
    try:
        n = client.models.count_tokens(model=m.GEMINI_MODELS[0], contents=types.Content(
            parts=[types.Part(file_data=types.FileData(file_uri=url))]))
        print(f"  토큰 수: {n.total_tokens:,} (한도 약 1,000,000)", flush=True)
    except Exception as e:
        print(f"  토큰 수 확인 실패: {type(e).__name__}: {str(e)[:100]}", flush=True)
    t = time.time()
    try:
        info = m.summarize_with_video(url, CH, label, "")
        print(f"  요약 OK {time.time() - t:.0f}s: {info.get('title')} / {info.get('scripture')} / {info.get('preacher')}", flush=True)
    except Exception as e:
        print(f"  요약 실패 {time.time() - t:.0f}s: {type(e).__name__}: {str(e)[:120]}", flush=True)
