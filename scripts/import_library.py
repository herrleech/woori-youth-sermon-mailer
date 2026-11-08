"""library/*.json 을 Firestore sermons/{영상ID} 로 옮긴다 (여러 번 실행해도 안전: 같은 문서를 덮어쓴다).

필요: 환경변수 FIREBASE_SERVICE_ACCOUNT (GitHub Secret). 키 값은 출력하지 않는다.
"""
import json
import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not raw:
    sys.exit("FIREBASE_SERVICE_ACCOUNT 환경변수가 없습니다")
firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
db = firestore.client()

files = sorted((Path(__file__).resolve().parent.parent / "library").glob("*.json"))
records = []
for f in files:
    r = json.loads(f.read_text(encoding="utf-8-sig"))
    r.setdefault("channel", "청년교구")  # 채널 필드가 생기기 전에 저장된 설교는 모두 청년교구
    records.append(r)

for i in range(0, len(records), 400):  # 배치 한 번에 최대 500건
    batch = db.batch()
    for r in records[i:i + 400]:
        batch.set(db.collection("sermons").document(r["video_id"]), {**r, "updatedAt": firestore.SERVER_TIMESTAMP})
    batch.commit()

stored = sum(1 for _ in db.collection("sermons").select([]).stream())
print(f"library 파일 {len(records)}개 -> Firestore sermons 문서 {stored}개 (채널: "
      f"{sorted({r['channel'] for r in records})})")
sample = db.collection("sermons").document(records[-1]["video_id"]).get().to_dict() or {}
print("샘플 확인:", sample.get("video_id"), "|", sample.get("title"), "|", sample.get("channel"))
