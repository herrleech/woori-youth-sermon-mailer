# 한 구절 묵상 · 설교 자동 라이브러리 (사용 설명서)

분당우리교회 유튜브 채널(**청년교구** `@woori_youth`, **본채널** `@BundangWooriChurch`)에 새 설교가 올라오면
AI(Gemini)가 요약해서 **이메일로 보내고**, 앱의 **설교 라이브러리**에 저장하고, **푸시 알림**을 보냅니다.
QT·설교 노트와 한 앱으로 묶여 있고, 폰에는 APK로 설치합니다. 전부 무료 한도 안에서 GitHub 서버가 돌립니다 (내 PC는 꺼져 있어도 됩니다).

| 무엇 | 어디 |
|---|---|
| 앱(웹) | https://qtsermon.web.app |
| 폰 앱(APK) 최신본 | https://github.com/herrleech/woori-youth-sermon-mailer/releases/latest/download/qtsermon.apk |
| 공개 설교 대시보드(옛 화면) | https://herrleech.github.io/woori-youth-sermon-mailer/ |
| 저장소 | https://github.com/herrleech/woori-youth-sermon-mailer |

## 1. 구성

```
유튜브 새 영상 ─▶ check-new-sermon(GitHub Actions) ─▶ Gemini 요약 ─┬▶ 이메일(설교마다 1통)
                                                                  ├▶ library/*.json (+ 공개 대시보드 docs/)
                                                                  ├▶ Firestore sermons  ─▶ 앱 "설교" 탭
                                                                  └▶ 푸시 알림(앱에서 켠 기기)
QT 본문 ─▶ qt-daily ─▶ Firestore qt ─▶ 앱 "오늘" 탭      노트/QT 기록 ─▶ Firestore users/{나}/… (본인 구글 계정만 접근)
```

## 2. 자동으로 도는 작업 (한국 시간)

| 시각 | 작업 | 하는 일 |
|---|---|---|
| 01:00 | `qt-daily` | 그날 QT 본문을 가져와 Firestore에 저장 |
| 03:00 | `backfill-library` | 지난 청년교구 설교를 하루 3편씩 요약해 라이브러리에 추가 (메일 없음) |
| 07:13 | `push-notify` | "오늘의 QT" 푸시 알림 |
| 11:17~23:17 매시, 23:47 | `check-new-sermon` | 새 설교 확인 → 요약 → 메일 · 라이브러리 · 푸시 |
| (코드 올릴 때) | `qt-deploy`, `android-build` | 사이트 배포 / APK 빌드 |

> **알려진 한계: GitHub는 예약 실행을 자주 건너뜁니다.** 실측으로 설교 확인은 하루 14회 설정에 **하루 1~3회**만 돌았습니다.
> 그래서 새 설교 메일이 몇 시간 늦거나 한꺼번에 올 수 있습니다. 급하면 수동 실행(아래 5번)을 쓰세요.
> 근본 해결은 GitHub 밖의 무료 시계(예: Cloudflare Workers Cron)가 매시간 `check.yml`을 깨우게 하는 것입니다 (계정 + 이 저장소 전용 토큰 필요).

## 3. 폰 앱 (APK)

- **설치**: 위 APK 링크를 폰에서 열어 받아 설치합니다. ("출처를 알 수 없는 앱" 허용, Play Protect 경고는 "그래도 설치")
- **업데이트**: 화면·기능·요약 형식 등 **대부분의 수정은 재설치가 필요 없습니다.** 사이트에 배포되면 앱을 닫았다 열 때 반영됩니다.
  아이콘·이름·상태 표시줄 색처럼 **APK 자체를 바꿀 때만** 새 APK를 위에 설치합니다 (지우지 마세요. 같은 서명 키라 덮어쓰기가 됩니다).
- 앱은 폰의 **Chrome**으로 열립니다. 평소 쓰던 브라우저와 별개라서 앱에서 **다시 로그인하고 알림도 다시 켜야** 합니다.
  알림이 두 번 오지 않게, 앱에서 켠 뒤 브라우저 쪽 알림은 끄세요 (설정 → 알림).
- **화면 테마**: 앱 → 설정 → 화면 (시스템 설정 / 라이트 / 다크).

## 4. 자주 바꾸는 설정

| 바꾸고 싶은 것 | 방법 |
|---|---|
| 메일 받는 사람 | 터미널에서 `gh secret set MAIL_TO` (여러 명은 쉼표로 구분). **받는 사람 동의를 먼저 받으세요** |
| 메일 제외할 영상 종류 | `sermon_mailer.py`의 `EXCLUDE_KEYWORDS` (지금: 새벽기도회). 생방송/라이브/🔴 제목은 자동 제외 |
| 설교로 보는 기준 | `SERMON_KEYWORDS` (제목에 목사/전도사/강도사) |
| 채널 추가 | `sermon_mailer.py`의 `CHANNELS`에 채널 ID 추가 (`library: True`면 라이브러리·앱에도 저장). 처음 확인 때 기존 영상은 메일 없이 기록만 합니다 |
| 확인 주기 | `.github/workflows/check.yml`의 `cron` (UTC 기준, 한국 시간 −9시간) |
| 하루 백필 개수 | `.github/workflows/backfill.yml`의 `BACKFILL` |
| QT 알림 시각 | `.github/workflows/push.yml`의 `cron` |
| Gemini 모델 순서 | `sermon_mailer.py`의 `GEMINI_MODELS` (바뀌면 `gemini-probe`로 다시 측정) |

## 5. 수동 실행 (GitHub → Actions 탭, 또는 터미널)

```bash
gh workflow run check.yml                                  # 지금 바로 새 설교 확인
gh workflow run check.yml -f test_video=영상ID             # 영상 1개를 테스트 메일로 (기록은 안 건드림)
gh workflow run check.yml -f library_videos=영상ID,영상ID  # 메일 없이 라이브러리/앱에만 추가
gh workflow run push.yml -f mode=test                      # 테스트 푸시 알림 (mode=qt-reminder 도 가능)
gh workflow run gemini-probe.yml                           # 지금 쓸 수 있는 Gemini 모델 측정
```

| 워크플로 | 용도 |
|---|---|
| `restructure-library` | 소제목 없는 예전 요약을 소제목+문단으로 정리 (영상은 다시 안 봄) |
| `import-library` | `library/*.json` → Firestore 일괄 이전 (여러 번 실행해도 안전) |
| `diag-gcp` | Firebase 프로젝트의 API 활성화 상태 조회 (읽기 전용) |
| `import-bible` | 새번역 성경 1회 가져오기 |
| `android-build` | APK 빌드 (`android/` 폴더를 바꾸면 자동 실행) |

## 6. 비밀 값과 백업 (가장 중요)

GitHub Secrets에 들어 있는 값: `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `MAIL_TO`,
`FIREBASE_SERVICE_ACCOUNT`, `WEBPUSH_VAPID_PRIVATE`, `ANDROID_KEYSTORE_B64`, `ANDROID_KEYSTORE_PASSWORD`.
Secret은 읽어낼 수 없으므로 **아래 파일은 PC의 `.secrets/` 폴더 밖 두 곳(비밀번호 관리자 + 드라이브/USB)에 백업**해 두세요. 이 폴더는 git에 올라가지 않습니다.

| 파일 | 잃어버리면 |
|---|---|
| `.secrets/release.p12` + `keystore_password.txt` | **같은 앱으로 업데이트 불가.** 앱을 지우고 새 키로 새로 설치해야 합니다 (데이터는 구글 계정에 있어 안전). `assetlinks.json` 지문도 새로 바꿔야 합니다 |
| `.secrets/vapid_private.txt` | 새 푸시 키를 만들고 앱의 공개 키(`firebase-config.js`)를 바꾼 뒤, 기기마다 알림을 다시 켜야 합니다 |

## 7. 문제 해결

| 증상 | 확인 |
|---|---|
| 새 설교 메일이 안 옴 | ① 영상 제목에 "목사/전도사/강도사"가 있고 생방송·새벽기도회가 아닌지 ② Actions → `check-new-sermon` 로그의 "요약 실패" 줄 ③ Gemini가 막혔으면 `gemini-probe` 실행 후 `GEMINI_MODELS` 조정 ④ 예약이 건너뛰어졌으면 수동 실행 |
| 요약이 계속 실패 | 2일이 지나면 제목·링크만 담은 안내 메일이 갑니다. 영상이 방금 올라온 라이브 다시보기면 몇 시간 뒤 자동으로 풀리는 경우가 많습니다 |
| 알림이 안 옴 | 앱 설정 → 알림이 켜져 있는지, 폰/브라우저의 알림 허용, `push-notify`를 `mode=test`로 실행해 "성공 1" 이상인지 |
| 앱에서 로그인이 안 됨 | 앱은 Chrome 기반이라 팝업 로그인이 막힐 수 있습니다. 증상(오류 문구)을 알려주면 다른 로그인 방식으로 바꿀 수 있습니다 |
| GitHub에서 "Run failed" 메일이 옴 | 어느 워크플로인지 제목을 확인. 설교 메일러(`check-new-sermon`)가 반복해서 실패할 때만 신경 쓰면 됩니다 |

## 8. 비용 · 한도 · 주의

- 모두 무료 한도 안입니다: Gemini 무료 키(하루 요약 약 4~5편 사용, 한도 걸리면 다음 실행에서 재시도), YouTube Data API, Firebase 무료 요금제, GitHub Actions(공개 저장소).
- **저작권**: 앱에는 새번역 성경 본문과 교회 QT 본문이 들어 있습니다. **본인 전용**으로만 쓰고 공개 배포하지 마세요. 앱 데이터는 본인 구글 계정만 읽도록 Firestore 규칙으로 막혀 있습니다.
- 저장소가 **공개**라서 코드, 설교 요약(`library/`, `docs/`), 본인 이메일(`qt-app/firestore.rules`)이 보입니다. 비밀번호·키는 보이지 않습니다.
- APK 릴리스도 공개라 누구나 받을 수 있지만, 로그인한 본인 계정만 데이터를 볼 수 있습니다.
- AI 요약은 부정확할 수 있습니다 (메일 하단에도 표시).

## 9. 폴더 안내

`sermon_mailer.py` 새 설교 확인·요약·메일 · `push.py` 푸시 발송 · `build_site.py` 공개 대시보드 데이터 ·
`scripts/` 보조 스크립트 · `library/` 설교 요약 JSON · `qt-app/web/` 앱(웹) · `qt-app/scraper/` QT 수집 · `android/` APK 프로젝트 ·
`.github/workflows/` 자동 작업 · `docs/` 공개 대시보드 · `.secrets/` 내 PC에만 있는 비밀 파일 (git 제외)
