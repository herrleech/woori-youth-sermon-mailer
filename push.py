"""FCM 웹 푸시 발송 (Firebase Admin SDK). 알림을 받을 기기는 앱이 Firestore users/{uid}/devices/{토큰} 에 등록한다.

메시지는 data 전용으로 보낸다: 앱의 서비스워커(sw.js)가 title/body/hash 를 읽어 직접 알림을 띄운다.
"""
import sys


def device_targets(db, kind):
    """kind(예: newSermon, qtReminder) 알림을 켜둔 기기 목록 [(문서 참조, 토큰)]. 필드가 없으면 켜진 것으로 본다."""
    out = []
    for d in db.collection_group("devices").stream():
        x = d.to_dict() or {}
        if x.get("token") and x.get(kind, True):
            out.append((d.reference, x["token"]))
    return out


def send(db, kind, title, body, hash_, tag=None, dry_run=False):
    """등록된 기기 모두에게 보낸다. (성공, 실패, 만료되어 정리한 기기) 수를 돌려준다. dry_run 이면 검증만 하고 실제로 보내지 않는다."""
    from firebase_admin import messaging

    sent = failed = removed = 0
    for ref, token in device_targets(db, kind):
        msg = messaging.Message(
            data={"title": title, "body": body, "hash": hash_, "tag": tag or kind},
            token=token,
            webpush=messaging.WebpushConfig(headers={"Urgency": "high", "TTL": "86400"}),
        )
        try:
            messaging.send(msg, dry_run=dry_run)
            sent += 1
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError):  # 앱을 지웠거나 토큰이 만료된 기기
            if not dry_run:
                ref.delete()
            removed += 1
        except Exception as e:
            print(f"푸시 실패: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
            failed += 1
    return sent, failed, removed
