# vendor/ — 앱에 포함한 외부 라이브러리 (오프라인에서도 열리도록 CDN 대신 직접 포함)

| 파일 | 출처 | 버전 | 라이선스 |
|---|---|---|---|
| `quill.js`, `quill.snow.css` | https://cdn.jsdelivr.net/npm/quill@2.0.3/dist/ | 2.0.3 | BSD-3-Clause |
| `firebase/firebase-app.js`, `firebase-auth.js`, `firebase-firestore.js`, `firebase-messaging.js` | https://www.gstatic.com/firebasejs/10.14.1/ | 10.14.1 | Apache-2.0 |

- `firebase-auth.js`, `firebase-firestore.js`, `firebase-messaging.js` 안의 `import ... "https://www.gstatic.com/firebasejs/10.14.1/firebase-app.js"` 는
  `"./firebase-app.js"` 로 바꿔 두었다 (그 외 수정 없음). `quill.js` 끝의 sourceMappingURL 주석만 제거했다.
- 버전을 올릴 때: 위 주소의 버전 숫자만 바꿔 다시 받고, 같은 import 치환을 한 뒤 `sw.js` 의 `CACHE` 버전을 올린다.
