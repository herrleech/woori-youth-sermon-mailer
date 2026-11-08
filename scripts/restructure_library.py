"""예전 형식(소제목 없는) 요약을 소제목 + 문단 구조로 다시 정리한다. 영상은 보지 않고 기존 요약 글만 사용한다.

- points(소제목) 가 이미 있는 설교는 건너뛴다 -> 여러 번 실행해도 안전하다.
- 원본 요약은 summary_old 에 남긴다. 변환에 실패한 설교는 그대로 두고 다음 실행에서 다시 시도한다.
- library/*.json 과 Firestore(sermons) 를 함께 갱신한다. (GEMINI_API_KEY 필요, FIREBASE_SERVICE_ACCOUNT 는 선택)
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sermon_mailer as m  # noqa: E402

PROMPT = """다음은 교회 설교 영상의 기존 요약입니다. 이 요약에 들어 있는 내용만 사용해서 읽기 좋은 구조로 다시 정리하세요.
새로운 사실, 예화, 성경 구절을 지어내거나 덧붙이지 마세요. 아래 JSON 객체 하나로만 답하세요 (목록이 아니라 객체).
- key_message: 설교의 핵심 메시지 한 문장 (60자 이내)
- points: 요약의 흐름을 3~5개 요점으로 나눈 객체 배열. 각 객체는 heading(요점 소제목, 20자 이내)과 body(그 요점의 설명)를 가진다.
  body는 기존 요약의 문장과 표현을 최대한 살려 자연스럽게 이어 쓴다.

설교 제목: {title}
성경 본문: {scripture}
설교자: {preacher}

기존 요약:
{summary}
"""


def main():
    limit = int(os.environ.get("RESTRUCTURE_LIMIT", "200"))
    todo = []
    for f in sorted(m.LIBRARY_DIR.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8-sig"))
        if not r.get("points") and r.get("summary"):
            todo.append((f, r))
    print(f"소제목 형식이 아닌 설교 {len(todo)}편 (이번 실행 최대 {limit}편)")

    done = failed = 0
    for f, r in todo[:limit]:
        try:
            data = m.generate_json(PROMPT.format(title=r.get("title", ""), scripture=r.get("scripture", ""),
                                                 preacher=r.get("preacher", ""), summary=r["summary"]))
        except Exception as e:
            print(f"실패(건너뜀): {r.get('title')} - {type(e).__name__}", file=sys.stderr)
            failed += 1
            continue
        if not data.get("points"):  # 모델이 소제목 구조를 못 만든 경우: 원본을 건드리지 않는다
            print(f"소제목 구조를 얻지 못함(건너뜀): {r.get('title')}", file=sys.stderr)
            failed += 1
            continue
        new = {**r, "channel": r.get("channel", "청년교구"), "summary_old": r["summary"],
               "key_message": data["key_message"], "points": data["points"], "summary": data["summary"]}
        f.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
        m.save_to_firestore(new)
        done += 1
        print(f"재구성 완료 ({done}): {r.get('title')}")
        time.sleep(2)  # 분당 요청 한도 보호
    print(f"결과: 재구성 {done}편, 실패/건너뜀 {failed}편, 남은 대상 {max(0, len(todo) - done)}편")


if __name__ == "__main__":
    main()
