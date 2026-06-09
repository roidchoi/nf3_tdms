# 인터페이스: 헬스 및 어드민 API (health_admin_api.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-09 (Task-006)  
> **물리 경로**: 
> - `tdms_core/p3_usdms/routers/health.py`
> - `tdms_core/p3_usdms/routers/admin.py`
> **상태**: ✅ 완료

---

## 1. 개요
USDMS 시스템의 데이터 최신성(Freshness), 수집 누락(Gaps), 수집 차단 상태(Blacklist)를 확인하는 헬스 API와 수집 태스크 상태 조회, 스케줄링 동적 제어, 실시간 수집 로그 전송(WebSocket)을 지원하는 어드민 API 인터페이스를 명세합니다.

---

## 2. 헬스 API 엔드포인트 (`/api/health`)

### ① `GET /freshness`
미국 영업일 캘린더(`trading_calendar`)를 기준으로 최신 영업일 대비 활성 종목의 일봉 수집 완료율을 판정하여 상태를 반환합니다.
* **임계치 기준**:
  - 한국 시각 **오전 07:00 KST** 이전: 수집 진행 중이므로 전영업일 기준 95% 완료율 도달 시 GREEN 판정.
  - 한국 시각 **오전 07:00 KST** 이후: 수집 완료 시점이므로 당일 영업일 기준 95% 이상 시 GREEN 판정.
  - 최종 판정 등급: 98% 이상 `GREEN`, 95% 이상 98% 미만 `YELLOW`, 95% 미만 `RED`
* **반환 예시**:
  ```json
  {
    "status": "GREEN",
    "latest_trading_date": "2026-06-03",
    "total_active_stocks": 3909,
    "collected_daily_count": 3890,
    "daily_coverage_ratio": 0.9951,
    "is_daily_fresh": true
  }
  ```

### ② `GET /gaps`
지정 기간(`start_date` ~ `end_date`) 동안 수집 대상 종목의 일봉 누락을 탐지하여 반환합니다.
* **실질 누락율 공식**:
  - 거래량 0인 거래정지 종목 및 블랙리스트 등록 종목은 모수 및 실패 카운트에서 배제하여 허위 경보를 차단합니다.
* **반환 예시**:
  ```json
  {
    "start_date": "2026-06-03",
    "end_date": "2026-06-03",
    "minute_gaps": [
      {
        "date": "2026-06-03",
        "total_targets": 3909,
        "valid_targets": 3900,
        "collected_count": 3900,
        "valid_collection_rate": 100.0,
        "gaps_count": 0
      }
    ]
  }
  ```

### ③ `GET /blacklist`
현재 차단된 상태(`is_blocked=True`)인 수집 블랙리스트 상세 내역 목록을 반환합니다.

### ④ `POST /blacklist/{cik}/release`
특정 CIK(`10자리` 보장)의 블랙리스트 수집 차단을 강제로 해제합니다.
* **동작 메커니즘**:
  - `is_blocked` 필드를 `False`로 변경하고, `release_date`에 현재 시각 기록 및 메모(`detail`)에 관리자 릴리즈 내역을 덧붙입니다.
  - 다음 수집 스케줄 실행 시 해당 종목의 수집이 재시도됩니다. (실패 횟수는 0으로 초기화됨)
* **요청 예시**:
  `POST /api/health/blacklist/0000320193/release`
* **반환 예시**:
  ```json
  {
    "status": "success",
    "released_cik": "0000320193"
  }
  ```

---

## 3. 어드민 API 엔드포인트 (`/api/admin`)

### ① `GET /tasks/status`
`logs/` 디렉토리에 적재된 최근 10건의 수집/백필 실행 이력 리포트 JSON 파일 목록을 최신 타임스탬프 역순으로 반환합니다.

### ② `GET /schedules`
APScheduler에 등록된 크론 작업의 식별 ID, 다음 실행 예정 시각, 크론 트리거 설정을 조회합니다.

### ③ `PUT /schedules`
크론 작업(`job_id`)의 매일 실행 시간(`hour`, `minute`)을 동적으로 변경(reschedule)합니다.

### ④ `WebSocket /ws/logs`
지정한 파일명 또는 가장 최신의 수집 로그 파일(`.log`)을 대상으로 `tail -f` 방식의 실시간 라인 전송 비동기 커넥션을 유지합니다.
* **통신 프로토콜**:
  - 연결 승인 직후 기존 마지막 100줄을 읽어 클라이언트에 전송합니다.
  - 그 후 비동기 폴링을 통해 추가되는 로그 라인을 즉시 실시간 텍스트 프레임으로 푸시합니다.
