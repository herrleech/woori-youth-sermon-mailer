"""표준 웹 푸시(VAPID) 발송. 알림을 받을 기기(브라우저 푸시 구독)는 앱이 Firestore users/{uid}/devices/{해시} 에 등록한다.

- 비공개 VAPID 키는 환경변수 WEBPUSH_VAPID_PRIVATE (GitHub Secret). 짝이 되는 공개 키는 앱(firebase-config.js)에 있다.
- 메시지는 JSON {title, body, hash, tag}. 앱의 서비스워커(sw.js)가 읽어 알림으로 띄운다.
- Firebase 메시징 API 를 쓰지 않는다 (토큰 등록 API 가 401 로 거부되는 문제를 피하려고).
"""
import json
import os
import sys

SUBJECT = "https://qtsermon.web.app"  # VAPID 'sub' (연락처 URL)


def device_targets(db, kind):
    """kind(예: newSermon, qtReminder) 알림을 켜둔 기기 목록 [(문서 참조, 구독 정보)]. 필드가 없으면 켜진 것으로 본다."""
    out = []
    for d in db.collection_group("devices").stream():
        x = d.to_dict() or {}
        keys = x.get("keys") or {}
        if x.get("endpoint") and keys.get("p256dh") and keys.get("auth") and x.get(kind, True):
            out.append((d.reference, {"endpoint": x["endpoint"], "keys": {"p256dh": keys["p256dh"], "auth": keys["auth"]}}))
    return out


def send(db, kind, title, body, hash_, tag=None, dry_run=False):
    """등록된 기기 모두에게 보낸다. (성공, 실패, 만료되어 정리한 기기) 수를 돌려준다.
    dry_run 이면 대상 선별과 메시지 암호화까지만 확인하고 실제로 보내지 않는다."""
    from pywebpush import WebPusher, WebPushException, webpush

    private = os.environ.get("WEBPUSH_VAPID_PRIVATE")
    if not private:
        raise RuntimeError("WEBPUSH_VAPID_PRIVATE 가 설정되지 않았습니다 (GitHub Secret 필요)")
    data = json.dumps({"title": title, "body": body, "hash": hash_, "tag": tag or kind}, ensure_ascii=False)

    sent = failed = removed = 0
    for ref, sub in device_targets(db, kind):
        try:
            if dry_run:
                WebPusher(sub).encode(data.encode("utf-8"))      # 구독 키로 암호화가 되는지만 확인
            else:
                webpush(subscription_info=sub, data=data, vapid_private_key=private,
                        vapid_claims={"sub": SUBJECT},          # aud 가 채워지므로 호출마다 새 dict
                        ttl=86400, headers={"Urgency": "high"}, timeout=20)
            sent += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):                             # 앱을 지웠거나 구독이 만료된 기기
                if not dry_run:
                    ref.delete()
                removed += 1
            else:
                print(f"푸시 실패(HTTP {status}): {str(e)[:150]}", file=sys.stderr)
                failed += 1
        except Exception as e:
            print(f"푸시 실패: {type(e).__name__}: {str(e)[:150]}", file=sys.stderr)
            failed += 1
    return sent, failed, removed


def public_key_of(private):
    """비공개 키에서 공개 키(앱에 들어가는 값, base64url)를 계산한다. 앱 설정과 짝이 맞는지 확인할 때 쓴다."""
    import base64

    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    pub = Vapid.from_string(private).public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(pub).decode().rstrip("=")
