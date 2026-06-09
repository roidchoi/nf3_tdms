# 인터페이스: 미국 CIK 차단 해제 중계 API (post_blacklist_release.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-09 (Task-006)  
> **물리 경로**: `tdms_core/p4_manager/routers/manager.py` (라인 296-317)
> **상태**: ✅ 완료

---

## 1. 개요
미국 백엔드(USDMS)의 CIK 수집 차단 블랙리스트 해제 요청 API를 P4 매니저 백엔드에서 중계 처리합니다.
프론트엔드(`BlacklistPanel.vue`)의 승인 다이얼로그 모달을 통해 전달된 특정 CIK의 차단을 해제하여 다음 배치 스케줄 기동 시 재수집하도록 허용합니다.

---

## 2. API 규격

### POST `/api/mgr/health/us/blacklist/{cik}/release`
* **Path Parameters**:
  - `cik`: 차단을 해제할 미국의 10자리 CIK 코드 (예: `0000320193`)
* **요청 예시**:
  `POST /api/mgr/health/us/blacklist/0000320193/release`
* **출력 형식**:
  - 반환 타입: `dict` (JSON)
  - 응답 상태코드: `200 OK` (성공) / `502 Bad Gateway` (하위 서버 오프라인 또는 통신 실패)

#### 정상 반환 스키마
```json
{
  "status": "success",
  "released_cik": "0000320193"
}
```
* **동작 세부**: P3 USDMS 백엔드의 `/api/health/blacklist/{cik}/release` API를 호출하고 결과를 반환합니다.
* **장애 격리**: 릴리즈 액션은 단순 조회가 아니므로 통신 실패 시 `200 OK offline fallback` 대신 `502 Bad Gateway` 및 통신 에러 문구를 포함한 HTTP 예외를 발생시켜 클라이언트 측에서 명확하게 등록 실패를 인지하게 만듭니다.
