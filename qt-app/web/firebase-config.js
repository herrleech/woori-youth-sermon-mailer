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

// 웹 푸시 공개 키 (Firebase 콘솔 > 프로젝트 설정 > 클라우드 메시징 > 웹 푸시 인증서의 "키 쌍"). 공개 값이라 코드에 둬도 된다.
// 비어 있으면 설정 화면의 알림 항목이 "준비 중"으로 표시된다.
export const vapidKey = "BG2Ak99YeZBw3LzJgctOvH5mEUYvuF-pASA_g7VSr-1w3MhI4Jdj3zBYW322ElpGI3wUUcEZkIn89f2PXeTLARQ";
