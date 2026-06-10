# Task-007: 데이터 익스플로러 테이블 동적 미리보기

> **Sub Project**: p4_manager (통합 관리 레이어)
> **PRD 근거**: F-10 (테이블 미리보기)
> **작성일**: 2026-06-10
> **의존 Task**: T-006 (공통 헬스 모니터링 및 시장별 특화 패널)

---

## [위키 선조회 완료]

> 이 표는 Spec 작성 전 nf-wiki 조회 완료를 확인하는 필수 항목입니다.
> `references/wiki-query-protocol.md` 절차를 따랐음을 선언합니다.

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| .env 변수명 | `pjt_wiki/p4_manager_wiki/environment.md` | ✅ 확인 |
| config.py 설정 | 위키 미기록 → `tdms_core/p4_manager/config.py` 직접 확인 | ⚠️ 직접 확인 |
| Nginx 리프록시 설정 | 위키 미기록 → `tdms_core/p4_manager/nginx/nginx.conf` 직접 확인 | ⚠️ 직접 확인 |
| KDMS preview API | `pjt_wiki/p2_kdms_wiki/interfaces/data_api_endpoints.md` | ✅ 확인 |
| USDMS preview API | `pjt_wiki/p3_usdms_wiki/interfaces/data_api_endpoints.md` | ✅ 확인 |
| 백엔드 중계 & 장애 격리 | `pjt_wiki/p4_manager_wiki/decisions.md` (P4DEC-002, P4DEC-003) | ✅ 확인 |
| 신규 중계 API 설계 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

각 시장별 백엔드(`p2_kdms`, `p3_usdms`)에서 관리하는 시세, 재무, 마스터, 시스템 정보 등 총 20종의 TimescaleDB 테이블 데이터를 통합 UI에서 동적으로 탐색하고 100건 단위로 미리보기 할 수 있는 탐색 도구를 구현합니다.

**구현 범위:**
- **IN**:
  - `p4_backend` 백엔드에 시장별 테이블 목록 메타데이터 조회 API (`GET /api/mgr/preview/meta`) 추가.
  - `p4_backend` 백엔드에 테이블 미리보기 데이터 비동기 중계 및 장애 격리 API (`GET /api/mgr/preview/{market}/{table}`) 추가.
  - `p4_frontend` 프론트엔드에 Pinia `explorerStore.ts` 추가.
  - `p4_frontend` 프론트엔드에 Glassmorphic 다크 테마 기반의 `ExplorerView.vue` 컴포넌트 추가 및 메인 대시보드 탭 연동.
  - `p4_backend` 에 대응하는 pytest 통합/단위 테스트 추가, `p4_frontend` 에 대응하는 vitest 컴포넌트 테스트 추가.
- **OUT**:
  - 테이블 데이터의 직접적인 수정, 삭제, 내보내기(CSV 등) 기능은 제외.
  - 1000건을 초과하는 대량 데이터의 페이징이나 무한 스크롤 성능 최적화는 제외 (최대 limit는 1000으로 제한).

---

## § 2. 구현 대상

### 신규 생성 파일
- `tdms_core/p4_manager/tests/test_explorer_bridge.py` — 중계 API 동작 및 장애 격리 검증을 위한 백엔드 테스트 파일
- `tdms_core/p4_manager/frontend/src/stores/explorerStore.ts` — 미리보기 데이터 조회 및 필터 상태를 관리하는 Pinia 스토어
- `tdms_core/p4_manager/frontend/src/views/ExplorerView.vue` — 테이블 드롭다운, 조건 필터, 동적 테이블 그리드, 페이지네이션을 포함하는 통합 탐색기 뷰
- `tdms_core/p4_manager/frontend/src/tests/ExplorerView.spec.ts` — 동적 테이블 렌더링, 필터 조작, 오프라인 UI 검증을 위한 Vitest 컴포넌트 테스트

### 수정 대상 파일
- `tdms_core/p4_manager/routers/manager.py` — 테이블 메타 및 미리보기 중계 엔드포인트 2종 추가
- `tdms_core/p4_manager/frontend/src/views/DashboardView.vue` — 메인 내비게이션 탭에 `🔍 데이터 익스플로러` 추가 및 activeTab 전환 분기 연동

---

## § 3. 핵심 인터페이스

구현 Agent가 코드를 작성하기 전에 인터페이스를 확정합니다.

### 3.1 테이블 메타데이터 스펙 (`GET /api/mgr/preview/meta`)
* **[신규 정의 — 구현 Agent가 아래 시그니처로 생성]**
* **역할**: 각 시장별 조회 가능한 테이블의 영문 식별자와 국문 명칭 리스트를 일관되게 반환합니다.
* **반환 구조 (JSON)**:
```json
{
  "kr": [
    { "table": "stock_info", "name": "종목 마스터 정보" },
    { "table": "daily_ohlcv", "name": "일봉 시세" },
    { "table": "daily_market_cap", "name": "일별 시가총액" },
    { "table": "minute_ohlcv", "name": "분봉 시세" },
    { "table": "financial_statements", "name": "PIT 재무제표" },
    { "table": "financial_ratios", "name": "PIT 재무비율" },
    { "table": "price_adjustment_factors", "name": "수정주가 팩터" },
    { "table": "system_milestones", "name": "수집 마일스톤 이력" },
    { "table": "trading_calendar", "name": "영업일 달력" },
    { "table": "minute_target_history", "name": "수집 대상 이력" }
  ],
  "us": [
    { "table": "us_ticker_master", "name": "미국 티커 마스터" },
    { "table": "us_ticker_history", "name": "티커 변경 이력" },
    { "table": "us_collection_blacklist", "name": "차단 종목 목록" },
    { "table": "us_financial_facts", "name": "SEC XBRL 수시 공시 재무 팩트" },
    { "table": "us_standard_financials", "name": "PIT 표준재무제표" },
    { "table": "us_share_history", "name": "주식수 변동 이력" },
    { "table": "us_daily_price", "name": "일봉 시세" },
    { "table": "us_price_adjustment_factors", "name": "수정주가 팩터" },
    { "table": "us_daily_valuation", "name": "일별 가치평가 지표" },
    { "table": "us_financial_metrics", "name": "분기별 재무비율" }
  ]
}
```

### 3.2 테이블 미리보기 중계 API (`GET /api/mgr/preview/{market}/{table}`)
* **[신규 정의 — 구현 Agent가 아래 시그니처로 생성]**
* **역할**: 선택된 시장 및 테이블에 대해 쿼리 매개변수 필터를 바인딩하여 하위 백엔드로 요청을 포워딩하고, 장애 발생 시 격리하여 폴백 객체를 반환합니다.
* **입력 매개변수**:
  - `market` (Path): `'kr'` 또는 `'us'`
  - `table` (Path): 조회할 테이블명
  - `limit` (Query): `int = 50` (최대 1000 제한)
  - `offset` (Query): `int = 0`
  - `stk_cd` (Query, Optional): 종목코드 필터
  - `start_date` (Query, Optional): YYYY-MM-DD 포맷 시작일
  - `end_date` (Query, Optional): YYYY-MM-DD 포맷 종료일
* **반환 구조 (정상 중계 시)**:
```json
{
  "offline": false,
  "table": "stock_info",
  "count": 2500,
  "data": [
    { "stk_cd": "005930", "stk_nm": "삼성전자", "is_active": true }
  ]
}
```
* **반환 구조 (장애 격리 시 - 200 OK 폴백)**:
```json
{
  "offline": true,
  "table": "stock_info",
  "count": 0,
  "data": [],
  "message": "http://p2_kdms:8000/api/data/preview/stock_info ConnectError"
}
```

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 및 파라미터 포워딩 케이스 (Tier 2)

```python
# [Tier 2 — 격리 통합]
def test_get_preview_metadata_success():
    """
    [목적] /api/mgr/preview/meta API 호출 시 각 시장의 허용 테이블 메타데이터 목록이 반환되는지 검증
    [유도] 정적 딕셔너리로 정의된 KR/US 테이블 메타데이터를 올바른 JSON 구조로 리턴하게 함
    """
    response = client.get("/api/mgr/preview/meta")
    assert response.status_code == 200
    data = response.json()
    assert "kr" in data
    assert "us" in data
    assert len(data["kr"]) == 10
    assert data["kr"][0]["table"] == "stock_info"

# [Tier 2 — 격리 통합]
def test_get_preview_table_kr_success(mock_respx):
    """
    [목적] 한국 백엔드의 preview API로 성공적으로 쿼리 파라미터를 넘기고 데이터를 수신하여 포맷팅하는지 검증
    [유도] httpx.AsyncClient를 이용하여 p2_kdms 백엔드로의 중계가 이루어지며, 응답에 offline: False가 부여되도록 유도
    """
    mock_respx.get("http://p2_kdms:8000/api/data/preview/stock_info?limit=10&offset=20&stk_cd=005930").respond(
        json={
            "table": "stock_info",
            "count": 1,
            "data": [{"stk_cd": "005930", "stk_nm": "삼성전자"}]
        },
        status_code=200
    )

    response = client.get("/api/mgr/preview/kr/stock_info?limit=10&offset=20&stk_cd=005930")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is False
    assert data["table"] == "stock_info"
    assert data["count"] == 1
    assert data["data"][0]["stk_cd"] == "005930"
```

### 4.2 입력 검증 및 오류 처리 케이스 (Tier 1)

```python
# [Tier 1 — 단위]
def test_get_preview_table_with_invalid_market_raises_bad_request():
    """
    [목적] 허용되지 않는 market 값(예: jp, cn) 입력 시 400 Bad Request 에러 반환 검증
    """
    response = client.get("/api/mgr/preview/jp/stock_info")
    assert response.status_code == 400
    assert "market" in response.json()["detail"].lower()

# [Tier 1 — 단위]
def test_get_preview_table_with_invalid_table_raises_bad_request():
    """
    [목적] 각 시장의 허용 화이트리스트에 없는 테이블명 입력 시 400 Bad Request 에러 반환 검증
    """
    # 한국에 us_ticker_master 요청 시
    response = client.get("/api/mgr/preview/kr/us_ticker_master")
    assert response.status_code == 400
    assert "not allowed" in response.json()["detail"].lower()
```

### 4.3 장애 격리(Fault Isolation) 케이스 (Tier 2)

```python
# [Tier 2 — 격리 통합]
def test_get_preview_table_offline_fallback(mock_respx):
    """
    [목적] 하위 백엔드가 오프라인 상태(Connection Error 또는 HTTP 503)일 때, 502/503을 전파하지 않고 200 OK와 offline: true 폴백 객체를 안전하게 리턴하는지 검증
    [유도] try-except 문으로 httpx.RequestError를 캐치하여 정규화된 오프라인 JSON 데이터 구조로 리턴하게 유도
    """
    # KDMS 연결 실패 시뮬레이션
    mock_respx.get("http://p2_kdms:8000/api/data/preview/daily_ohlcv").respond(status_code=503)

    response = client.get("/api/mgr/preview/kr/daily_ohlcv")
    assert response.status_code == 200
    data = response.json()
    assert data["offline"] is True
    assert data["table"] == "daily_ohlcv"
    assert data["count"] == 0
    assert len(data["data"]) == 0
    assert "message" in data
```

### 4.4 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest

@pytest.mark.integration
def test_get_preview_real_backend_integration():
    """
    [목적] 모킹 없이 실제 실행 중인 KDMS/USDMS 백엔드 컨테이너와 연동하여 테이블 조회 동작이 완전히 이루어지는지 검증
    [실행 조건] 실 백엔드 컨테이너 기동 필요. `pytest --run-integration`으로 실행.
    """
    # 실제 백엔드가 켜져 있을 때 한국의 stock_info 테이블 미리보기 데이터 1건을 조회
    response = client.get("/api/mgr/preview/kr/stock_info?limit=1")
    assert response.status_code == 200
    data = response.json()
    
    # 백엔드가 온라인인 경우 정상 필드를 단언하고, 오프라인인 경우 장애 격리 필드를 단언
    if data.get("offline"):
        assert data["offline"] is True
        assert data["count"] == 0
        assert len(data["data"]) == 0
    else:
        assert data["offline"] is False
        assert data["table"] == "stock_info"
        assert data["count"] >= 0
```

---

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_get_preview_metadata_success` | Tier 2 | 정상 | 각 시장별 테이블 메타데이터 제공 검증 |
| 2 | `test_get_preview_table_kr_success` | Tier 2 | 정상 | 한국 백엔드 테이블 데이터 조회 및 파라미터 전송 검증 |
| 3 | `test_get_preview_table_with_invalid_market_raises_bad_request` | Tier 1 | 예외 | 잘못된 마켓 파라미터 전달 시 400 에러 처리 검증 |
| 4 | `test_get_preview_table_with_invalid_table_raises_bad_request` | Tier 1 | 예외 | 화이트리스트에 없는 테이블명 입력 시 400 에러 처리 검증 |
| 5 | `test_get_preview_table_offline_fallback` | Tier 2 | 격리 | 하위 백엔드 오프라인 시 200 OK와 offline: true 반환 검증 |
| 6 | `test_get_preview_real_backend_integration` | Tier 3 | 실제 통합 | 모킹 없이 실제 기동 중인 백엔드 연결 및 장애 격리 연동 확인 |

**총 6개 테스트 — 전체 통과 시 Task 완료**
*(Tier 3는 `pytest --run-integration` 실행 시에만 포함)*

---

## § 5. 구현 참고사항

구현 Agent가 테스트를 통과시키는 과정에서 참고할 기술 정보입니다.
이 섹션은 구현 방법을 지시하지 않으며, 참고용으로만 활용합니다.

- **기술 스택**: 
  - Backend: FastAPI, httpx (비동기 HTTP 클라이언트)
  - Frontend: Vue 3, Pinia (상태 관리), Axios (서버 통신)
- **위키 참조 링크**:
  - `pjt_wiki/p2_kdms_wiki/interfaces/data_api_endpoints.md` — 한국 테이블 미리보기 엔드포인트 확인
  - `pjt_wiki/p3_usdms_wiki/interfaces/data_api_endpoints.md` — 미국 테이블 미리보기 엔드포인트 및 허용 목록 확인
  - `pjt_wiki/p4_manager_wiki/decisions.md` (P4DEC-002, P4DEC-003) — 장애 격리 설계 규칙 참조
- **주의사항**:
  - **종목 코드**: 한국의 종목 코드는 `stk_cd` 고정이지만 미국 시장은 테이블 스키마에 따라 `latest_ticker`, `ticker`, `cik` 등으로 상이하게 필터 조건이 적용됩니다. 하위 백엔드 preview API가 이미 해당 맵핑 처리를 지원하므로, 중계 시 쿼리 파라미터를 그대로 실어 보내면 됩니다.
  - **동적 헤더 렌더링**: 프론트엔드 UI 설계 시 테이블마다 컬럼 목록이 상이하므로 데이터 수신 후 첫 번째 레코드의 key 목록을 동적으로 추출하여 `<thead>`의 `<th>` 컬럼을 렌더링해야 합니다. 
  - **데이터 부재 대응**: 조회 결과 레코드가 없을 경우(data.length === 0)에는 key 목록을 추출할 수 없으므로, 빈 그리드와 함께 "조회된 데이터가 없습니다" 텍스트를 표출하도록 방어 코드를 구현합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] 프론트엔드 Vitest 컴포넌트 테스트 전체 통과
- [ ] `p4_manager_pjt_tasks.md`의 T-007 상태를 `완료`로 업데이트 (`docs/p4_manager/p4_manager_pjt_tasks.md`)
- [ ] `docs/p4_manager/tasks/task-007_walkthrough.md` 작성
