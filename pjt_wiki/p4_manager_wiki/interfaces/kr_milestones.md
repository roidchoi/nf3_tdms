# 인터페이스: 한국 마일스톤 생성 및 조회 중계 API (kr_milestones.md)

> **Sub Project**: p4_manager  
> **마지막 업데이트**: 2026-06-09 (Task-006)  
> **물리 경로**: `tdms_core/p4_manager/routers/manager.py` (라인 232-269)
> **상태**: ✅ 완료

---

## 1. 개요
한국 백엔드(KDMS)의 데이터 관리/정제 마일스톤 랜드마크 기록 정보를 P4 매니저에서 중계 조회하고, 신규 마일스톤을 추가/등록하는 API 스펙을 규정합니다.

---

## 2. API 규격

### 2.1. 한국 마일스톤 목록 조회
#### GET `/api/mgr/health/kr/milestones`
* **요청 예시**:
  `GET /api/mgr/health/kr/milestones`
* **출력 형식**:
  - 반환 타입: `list` (JSON)
  - 응답 상태코드: `200 OK` (성공)

##### 정상 반환 스키마 (예시)
```json
[
  {
    "milestone_name": "KDMS_INIT_2026",
    "milestone_date": "2026-06-01",
    "description": "한국 데이터베이스 연동 및 마일스톤 초기화",
    "updated_at": "2026-06-09T17:15:30Z"
  }
]
```
* **장애 격리**: KDMS 오프라인 시 빈 배열 `[]`을 반환하여 UI 오류 발생을 최소화합니다.

---

### 2.2. 한국 마일스톤 생성/수정
#### POST `/api/mgr/health/kr/milestones`
* **요청 바디 (JSON)**:
  ```json
  {
    "milestone_name": "KDMS_INIT_2026",
    "milestone_date": "2026-06-01",
    "description": "초기화 설명"
  }
  ```
* **출력 형식**:
  - 반환 타입: `dict` (JSON)
  - 응답 상태코드: `200 OK` (성공) / `502 Bad Gateway` (하위 백엔드 오프라인 혹은 통신 에러)

##### 정상 반환 스키마
```json
{
  "status": "success",
  "milestone": {
    "milestone_name": "KDMS_INIT_2026",
    "milestone_date": "2026-06-01",
    "description": "초기화 설명"
  }
}
```
* **장애 격리**: 릴리즈 액션과 마찬가지로, 생성 실패 시 클라이언트 측에서 파악하도록 `502 Bad Gateway` 예외를 노출합니다.
