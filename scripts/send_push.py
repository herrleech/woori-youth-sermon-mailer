"""푸시 알림 발송 스크립트.  MODE=qt-reminder | test,  DRY_RUN=1 이면 검증만(실제 발송 없음).

필요: FIREBASE_SERVICE_ACCOUNT (GitHub Secret). 키 값은 출력하지 않는다.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import push  # noqa: E402

raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not raw:
    sys.exit("FIREBASE_SERVICE_ACCOUNT 환경변수가 없습니다")
firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
db = firestore.client()

mode = (os.environ.get("MODE") or "qt-reminder").strip()
dry = os.environ.get("DRY_RUN") == "1"

if mode == "test":
    kind, title, body, hash_ = "test", "알림 테스트", "서버에서 보낸 테스트 알림입니다. 이 알림이 보이면 푸시가 정상입니다.", "#/settings"
elif mode == "qt-reminder":
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    doc = db.collection("qt").document(today).get()
    qt = doc.to_dict() if doc.exists else None
    kind, title, hash_ = "qtReminder", "오늘의 QT", f"#/qt/{today}"
    body = f"{qt.get('title', '')} · {qt.get('passage', '')}".strip(" ·") if qt else "오늘의 묵상을 확인해보세요"
else:
    sys.exit(f"알 수 없는 MODE: {mode}")

sent, failed, removed = push.send(db, kind, title, body, hash_, tag=kind + "-" + datetime.now(timezone.utc).strftime("%Y%m%d"), dry_run=dry)
print(f"[{mode}{' (검증만)' if dry else ''}] 대상 기기 성공 {sent}, 실패 {failed}, 만료 정리 {removed} | 제목: {title} | 내용: {body}")
if sent == 0 and failed == 0 and removed == 0:
    print("등록된 기기가 없습니다. 앱 설정 > 알림에서 '이 기기에서 알림 받기'를 먼저 켜주세요.")
    # 기기가 없어도 FCM 호출 권한/API 활성화 여부는 임시 토큰으로 점검할 수 있다 (dry_run: 실제로 보내지 않음)
    from firebase_admin import exceptions, messaging
    try:
        messaging.send(messaging.Message(data={"a": "b"}, token="x" * 163), dry_run=True)
        print("FCM 점검: 응답 OK")
    except (exceptions.InvalidArgumentError, messaging.UnregisteredError):
        print("FCM 점검: 정상 (임시 토큰이라 거부된 것은 예상된 결과 = FCM API/권한에 접근 가능)")
    except Exception as e:
        print(f"FCM 점검 실패: {type(e).__name__}: {str(e)[:300]}", file=sys.stderr)
        sys.exit(1)
if failed:
    sys.exit(1)
