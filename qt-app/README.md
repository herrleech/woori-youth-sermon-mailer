# 한 구절 묵상 (QT) PWA

분당우리교회 한 구절 묵상을 매일 06:00(KST) 수집 → Firestore → 어느 기기에서나 실시간 동기화되는 개인 QT 라이브러리 + 설교 메모.

## 처음 한 번만 설정
1. Firebase 프로젝트 생성 → Authentication(Google), Firestore, Storage, Hosting 활성화
   (신규 프로젝트의 Storage 는 Blaze 요금제 필요. 개인 사용량은 무료 한도 내)
2. 웹앱 등록 후 config 값을 `web/firebase-config.js` 에 붙여넣기
3. `firestore.rules`, `storage.rules` 의 이메일이 본인 구글 계정인지 확인 후 `firebase deploy` (qt-app 폴더에서)
4. 서비스 계정 키(JSON)를 GitHub 저장소 Secret `FIREBASE_SERVICE_ACCOUNT` 로 등록
5. Actions → `import-bible` 수동 실행 (새번역 전체 저장, 약 20~30분) / `qt-daily` 수동 실행(`backfill`=30 으로 과거 채우기)
6. 폰 Chrome 에서 호스팅 주소 접속 → 메뉴 → "홈 화면에 추가"

`firebase-config.js` 의 apiKey 가 비어 있으면 로컬 데모 모드(브라우저 저장소)로 동작합니다.

로컬 실행: `python -m http.server 8124 --directory qt-app/web`
