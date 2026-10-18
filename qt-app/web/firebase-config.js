// Firebase 웹앱 설정 (웹 apiKey 는 공개되어도 되는 식별자이며, 접근은 Firestore 규칙으로 제한됨)
// apiKey 가 비어 있으면 앱이 "로컬 데모 모드"(브라우저 저장소, 동기화 없음)로 동작합니다.
export const firebaseConfig = {
  apiKey: "AIzaSyA6B4S0mxHRTTtk0Z06B1TKAEFebZjQxGM",
  authDomain: "qtsermon.firebaseapp.com",
  projectId: "qtsermon",
  storageBucket: "qtsermon.firebasestorage.app",
  messagingSenderId: "420515596141",
  appId: "1:420515596141:web:9ad6cddfd0aa84f5d67c64",
};
