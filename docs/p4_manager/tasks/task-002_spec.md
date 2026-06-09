# Task-002: 백엔드 통합 상태 집계 서비스 개발

> **Sub Project**: p4_manager
> **PRD 근거**: F-01 (시스템 상태 개요), F-02 (태스크 상태 모니터링)
> **작성일**: 2026-06-09
> **의존 Task**: T-001 (개발 환경 및 인프라 구축)

---

## [위키 선조회 완료]

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| p2_kdms 헬스 API 경로 (`/api/health/freshness`) | `pjt_wiki/p2_kdms_wiki/interfaces/data_api_endpoints.md` | ✅ 확인 |
| p2_kdms 태스크 API 경로 (`/api/v1/admin/tasks/status`) | `tdms_core/p2_kdms/routers/admin.py` | ✅ 확인 |
| p3_usdms 헬스 API 경로 (`/api/health/freshness`) | `pjt_wiki/p3_usdms_wiki/interfaces/health_admin_api.md` | ✅ 확인 |
| p3_usdms 태스크 API 경로 (`/api/admin/tasks/status`) | `tdms_core/p3_usdms/routers/admin.py` | ✅ 확인 |
| .env 내 백엔드 연결 변수 (`P2_KDMS_URL`, `P3_USDMS_URL`) | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| Nginx 리버스 프록시 라우트 매핑 | `pjt_wiki/p4_manager_wiki/interfaces/api_routing_map.md` | ✅ 확인 |

---

## § 1. 목표

p2_kdms(한국) 및 p3_usdms(미국) 백엔드의 수집 상태, 데이터 최신성(Freshness), 배치 태스크 가동 현황 데이터를 백그라운드에서 비동기 폴링하여 캐싱하고, 양측의 서로 다른 API 경로 및 반환 포맷을 단일 공통 규격으로 정규화하여 대시보드용 `/api/mgr/status` 엔드포인트로 서빙한다. 특정 백엔드 장애(OFFLINE) 발생 시에도 타 백엔드 상태 서빙에 영향을 미치지 않도록 장애 격리(Fault Isolation)를 보장한다.

**구현 범위:**
- **IN**:
  - `tdms_core/p4_manager/config.py` (환경변수 설정 및 로드)
  - `tdms_core/p4_manager/services/status_service.py` (백그라운드 비동기 폴링 및 캐싱 로직)
  - `tdms_core/p4_manager/routers/manager.py` (`/api/mgr/status` 라우트 구현)
  - `tdms_core/p4_manager/main.py` (lifespan 내 백그라운드 폴링 태스크 기동 등록 및 라우터 마운트)
  - `tdms_core/p4_manager/tests/test_status.py` (T-002 비즈니스 로직 및 에러 처리 검증 TDD 테스트)
- **OUT**:
  - Vue3 프론트엔드 대시보드 UI 연동 및 컴포넌트 개발
  - 백업/복구 및 DB 물리 동기화 백엔드 API 구현 (F-11 ~ F-15)

---

## § 2. 구현 대상

### 신규 생성 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/config.py` — Pydantic-settings 기반 환경 변수 정의
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/status_service.py` — 비동기 HTTP 폴링 및 캐시 서비스
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py` — `/api/mgr/status` 통합 상태 조회 라우터
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_status.py` — 상태 집계 정상/예외/장애 테스트 코드

### 수정 대상 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/main.py` — lifespan 관리 및 신규 라우터 등록

---

## § 3. 핵심 인터페이스

구현 Agent는 아래 명시된 스키마와 설계 규칙을 준수하여 작성해야 합니다.

### 3.1 환경 설정 (`config.py`)
```python
# tdms_core/p4_manager/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    P2_KDMS_URL: str = "http://p2_kdms:8000"
    P3_USDMS_URL: str = "http://p3_usdms:8005"
    TASK_POLL_INTERVAL: int = 30  # 백그라운드 폴링 주기 (초)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
```

### 3.2 정규화 통합 상태 응답 스키마
`/api/mgr/status` 엔드포인트는 다음과 같이 통일된 규격으로 데이터를 정규화(Normalization)하여 반환해야 합니다.

```json
{
  "kr": {
    "status": "ONLINE" | "OFFLINE",
    "freshness": {
      "status": "GREEN" | "YELLOW" | "RED",
      "latest_trading_date": "YYYY-MM-DD",
      "daily_coverage_ratio": 0.985,
      "is_daily_fresh": true
    },
    "tasks": {
      "is_running": true | false,
      "last_run_time": "ISO-8601 string or null",
      "last_status": "success" | "failed" | "none"
    }
  },
  "us": {
    "status": "ONLINE" | "OFFLINE",
    "freshness": {
      "status": "GREEN" | "YELLOW" | "RED",
      "latest_trading_date": "YYYY-MM-DD",
      "daily_coverage_ratio": 0.965,
      "is_daily_fresh": true
    },
    "tasks": {
      "is_running": true | false,
      "last_run_time": "ISO-8601 string or null",
      "last_status": "success" | "failed" | "none"
    }
  }
}
```

* **정규화 매핑 규칙**:
  * **KR (p2) 태스크 맵핑**: p2가 반환하는 `Dict[str, Dict[str, Any]]` 구조에서 실행 중인 태스크가 있는지 여부를 확인하여 `is_running` 판정. 마지막 성공/실패 여부는 `daily_update` 또는 전체 태스크의 `last_status`를 기반으로 집계.
  * **US (p3) 태스크 맵핑**: p3가 반환하는 `List[Dict[str, Any]]` 구조(최신 로그 10건 목록)의 첫 번째 요소(최신 실행)를 바탕으로 현재 실행 중인 상태(`is_running`)와 최종 수행 결과를 분석하여 `last_run_time`, `last_status`를 파싱.

---

## § 4. 테스트 케이스

구현 Agent는 TDD 방식으로 아래 테스트를 순차 통과시켜 구현을 완성합니다.

### 4.1 정상 동작 케이스 (Tier 2)

```python
# tdms_core/p4_manager/tests/test_status.py
import pytest
import respx
from httpx import Response
from fastapi.testclient import TestClient
from tdms_core.p4_manager.main import app
from tdms_core.p4_manager.services.status_service import status_service

client = TestClient(app)

@pytest.mark.asyncio
@respx.mock
async def test_status_aggregation_success_normalizes_data():
    """
    [Tier 2 — 격리 통합]
    [목적] p2_kdms와 p3_usdms가 정상 응답할 때, status_service가 데이터를 가져와 규격에 맞게 캐싱 및 정규화하는지 검증.
    """
    # 1. KDMS (p2) Mock 응답 설정
    p2_freshness = {
        "status": "GREEN",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 2500,
        "collected_daily_count": 2490,
        "daily_coverage_ratio": 0.996,
        "is_daily_fresh": True
    }
    p2_tasks = {
        "daily_update": {"is_running": False, "last_status": "success", "last_run_time": "2026-06-08T17:05:00"},
        "financial_update": {"is_running": False, "last_status": "none"}
    }
    respx.get("http://p2_kdms:8000/api/health/freshness").mock(return_value=Response(200, json=p2_freshness))
    respx.get("http://p2_kdms:8000/api/v1/admin/tasks/status").mock(return_value=Response(200, json=p2_tasks))

    # 2. USDMS (p3) Mock 응답 설정
    p3_freshness = {
        "status": "YELLOW",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 6000,
        "collected_daily_count": 5800,
        "daily_coverage_ratio": 0.966,
        "is_daily_fresh": True
    }
    p3_tasks = [
        {"file_name": "daily_routine_2026-06-08.json", "status": "SUCCESS", "end_time": "2026-06-09T07:35:00", "is_running": False},
        {"file_name": "weekly_backfill_2026-06-06.json", "status": "SUCCESS", "end_time": "2026-06-06T09:40:00", "is_running": False}
    ]
    respx.get("http://p3_usdms:8005/api/health/freshness").mock(return_value=Response(200, json=p3_freshness))
    respx.get("http://p3_usdms:8005/api/admin/tasks/status").mock(return_value=Response(200, json=p3_tasks))

    # status_service 수동 갱신 실행
    await status_service.fetch_and_cache_status()

    # /api/mgr/status 호출 및 단언
    response = client.get("/api/mgr/status")
    assert response.status_code == 200
    data = response.json()

    # KR 검증
    assert data["kr"]["status"] == "ONLINE"
    assert data["kr"]["freshness"]["status"] == "GREEN"
    assert data["kr"]["freshness"]["daily_coverage_ratio"] == 0.996
    assert data["kr"]["tasks"]["is_running"] is False
    assert data["kr"]["tasks"]["last_status"] == "success"

    # US 검증
    assert data["us"]["status"] == "ONLINE"
    assert data["us"]["freshness"]["status"] == "YELLOW"
    assert data["us"]["freshness"]["daily_coverage_ratio"] == 0.966
    assert data["us"]["tasks"]["is_running"] is False
```

### 4.2 경계값 및 예외 케이스 (Tier 2)

```python
@pytest.mark.asyncio
@respx.mock
async def test_status_aggregation_handles_kr_offline_safely():
    """
    [Tier 2 — 격리 통합]
    [목적] p2_kdms가 다운되었거나 타임아웃(Connection Error) 발생 시, kr만 OFFLINE으로 표시하고 us 상태는 정상 제공하는지 장애 격리(Fault Isolation) 검증.
    """
    # KR (p2) 오프라인 모사 (타임아웃 유발)
    respx.get("http://p2_kdms:8000/api/health/freshness").mock(side_effect=Exception("Connection Timeout"))
    respx.get("http://p2_kdms:8000/api/v1/admin/tasks/status").mock(side_effect=Exception("Connection Timeout"))

    # US (p3) 정상 응답 모사
    p3_freshness = {
        "status": "GREEN",
        "latest_trading_date": "2026-06-08",
        "total_active_stocks": 6000,
        "collected_daily_count": 5950,
        "daily_coverage_ratio": 0.991,
        "is_daily_fresh": True
    }
    p3_tasks = []
    respx.get("http://p3_usdms:8005/api/health/freshness").mock(return_value=Response(200, json=p3_freshness))
    respx.get("http://p3_usdms:8005/api/admin/tasks/status").mock(return_value=Response(200, json=p3_tasks))

    # status_service 수동 갱신 실행
    await status_service.fetch_and_cache_status()

    response = client.get("/api/mgr/status")
    assert response.status_code == 200
    data = response.json()

    # KR 검증 (격리됨)
    assert data["kr"]["status"] == "OFFLINE"
    assert data["kr"]["freshness"] is None
    assert data["kr"]["tasks"] is None

    # US 검증 (정상 서빙)
    assert data["us"]["status"] == "ONLINE"
    assert data["us"]["freshness"]["status"] == "GREEN"
```

### 4.3 실제 통합 케이스 (Tier 3)

```python
@pytest.mark.integration
def test_real_backend_status_integration():
    """
    [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
    [목적] 실제 기동된 p2_kdms 및 p3_usdms 컨테이너를 상대로 상태를 폴링하여 ONLINE 여부를 검증.
    [주의] Nginx 및 p2, p3 컨테이너가 tdms-net 상에 구동되어 있어야 정상 통과함.
    """
    import httpx
    # Nginx 로컬 프록시 포트 80을 통해 호출
    response = httpx.get("http://localhost:80/api/mgr/status", timeout=5.0)
    assert response.status_code == 200
    data = response.json()
    
    # 두 시스템 키의 존재 유무 확인
    assert "kr" in data
    assert "us" in data
    
    # 켜져 있다면 ONLINE, 꺼져 있다면 OFFLINE 상태로 안정적으로 응답이 오는지만 검사
    assert data["kr"]["status"] in ["ONLINE", "OFFLINE"]
    assert data["us"]["status"] in ["ONLINE", "OFFLINE"]
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_status_aggregation_success_normalizes_data` | Tier 2 | 정상 | p2/p3 API 응답을 하나의 단일 정규화 스키마로 집계/매핑 검증 |
| 2 | `test_status_aggregation_handles_kr_offline_safely` | Tier 2 | 장애/예외 | 한 백엔드가 오프라인일 때, 예외 전파를 차단하고 나머지 백엔드만 정상 응답 검증 (서킷 브레이커) |
| 3 | `test_real_backend_status_integration` | Tier 3 | 실제 통합 | 실제 로컬/도커 환경에서 Nginx 게이트웨이를 경유하여 정상 데이터 수집 통합 테스트 |

**총 3개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **비동기 HTTP 클라이언트**: `httpx.AsyncClient`를 컨텍스트 매니저 또는 전역 단일 인스턴스로 사용하여 커넥션 재사용성을 높이고 비동기 병렬 요청(`asyncio.gather`)으로 대기 시간을 좁힙니다.
- **백그라운드 캐싱 타스크 설계**: 
  - FastAPI의 `lifespan` 관리 핸들러 내에서 비동기 무한 루프(`while True`) 태스크를 `asyncio.create_task`로 기동합니다.
  - 예시 스켈레톤:
    ```python
    import asyncio
    
    async def poll_status_loop():
        while True:
            try:
                await status_service.fetch_and_cache_status()
            except Exception as e:
                logger.error(f"Error in background polling: {e}")
            await asyncio.sleep(settings.TASK_POLL_INTERVAL)
    ```
- **타임아웃 제어**: `httpx.AsyncClient` 호출 시 개별 타임아웃을 `timeout=2.0`초 수준으로 짧게 잡아 타깃이 기동되지 않았을 때 백그라운드 태스크가 먹통되는 현상을 차단해야 합니다.

---

## § 6. 완료 기준

- [x] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [x] `pytest --run-integration` 실행 시 Tier 3 통합 테스트 통과
- [x] `/api/mgr/status` 호출 시 1ms 내외로 캐시 데이터 즉시 반환 확인
- [x] `docs/p4_manager/p4_manager_pjt_tasks.md`의 T-002 상태를 `완료`로 업데이트
- [x] `docs/p4_manager/tasks/task-002_walkthrough.md` 작성
