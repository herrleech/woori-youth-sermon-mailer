"""진단용(읽기 전용): Firebase 프로젝트의 Google API 활성화 상태와 API 키 제한을 조회한다. 키 값/비밀은 출력하지 않는다."""
import json
import os
import sys

import google.auth.transport.requests
from google.oauth2 import service_account

raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not raw:
    sys.exit("FIREBASE_SERVICE_ACCOUNT 환경변수가 없습니다")
info = json.loads(raw)
project = info["project_id"]
creds = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
sess = google.auth.transport.requests.AuthorizedSession(creds)
print("프로젝트:", project)


def get(url):
    r = sess.get(url, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:200]}


print("\n[1] Google API 활성화 상태 (ENABLED 여야 정상)")
for svc in ["fcmregistrations.googleapis.com", "fcm.googleapis.com", "firebaseinstallations.googleapis.com",
            "identitytoolkit.googleapis.com", "firestore.googleapis.com", "firebasehosting.googleapis.com"]:
    st, js = get(f"https://serviceusage.googleapis.com/v1/projects/{project}/services/{svc}")
    state = js.get("state") if st == 200 else f"조회 불가 (HTTP {st}: {js.get('error', {}).get('status')})"
    print(f"  {svc:42s} {state}")

print("\n[2] API 키 제한 (키 문자열은 출력하지 않음)")
st, js = get(f"https://apikeys.googleapis.com/v2/projects/{project}/locations/global/keys")
if st != 200:
    print(f"  조회 불가 (HTTP {st}: {js.get('error', {}).get('status')}) - 이 서비스 계정에는 키 조회 권한이 없음")
else:
    for k in js.get("keys", []):
        r = k.get("restrictions", {})
        print("  키:", k.get("displayName"), "| API 제한:", [t.get("service") for t in r.get("apiTargets", [])] or "없음(모든 API 허용)",
              "| 웹 사이트 제한:", r.get("browserKeyRestrictions", {}).get("allowedReferrers") or "없음")
