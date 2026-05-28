# Task-002: 일일 OHLCV + 종목 마스터 수집 (KIS)

> **Sub Project**: p2_kdms
> **PRD 근거**: F-01 (일일 OHLCV 수집), F-06 (종목 마스터 관리), API-데이터 (`/api/data/stocks`)
> **작성일**: 2026-05-14
> **의존 Task**: T-001

---

## § 1. 목표

KIS REST API를 통해 전체 상장 종목의 일봉 OHLCV와 종목 마스터를 수집하여 DB에 저장하고, `/api/data/stocks` 엔드포인트로 조회할 수 있다.

**구현 범위:**
- IN:
  - `collectors/kis_kr_client.py` — KisApiCore 래퍼, `start_date` 무시 페이지네이션 처리
  - `repositories/ohlcv_repo.py` — `daily_ohlcv` CRUD + gap 기록
  - `repositories/master_repo.py` — `stock_info` CRUD
  - `tasks/daily_task.py` — OHLCV + 종목마스터 수집 조율 (1차)
  - `routers/data.py` — `/api/data/stocks` 엔드포인트
- OUT:
  - 시가총액 수집, APScheduler 연동 (T-006)
  - 수정계수 수집·역산 API (T-003)
  - 수정주가 저장 테이블(`daily_ohlcv_adjusted`) 개설 및 CTE 기반 최근 N일 배치 갱신 (`refresh_adjusted_ohlcv_batch`) (-> T-003 수정계수 계산 및 저장의 구현 범위로 편입)

---

## § 2. 구현 대상

### 신규 생성 파일

```
tdms_core/p2_kdms/
├── collectors/
│   └── kis_kr_client.py           # KIS API 클라이언트 (OHLCV + 종목마스터)
├── repositories/
│   ├── ohlcv_repo.py              # daily_ohlcv CRUD + gap 기록
│   └── master_repo.py             # stock_info CRUD
├── tasks/
│   └── daily_task.py              # 일일 수집 조율 (1차: OHLCV + 종목마스터)
├── routers/
│   └── data.py                    # /api/data/stocks 엔드포인트
└── tests/
    ├── test_kis_kr_client.py
    ├── test_ohlcv_repo.py
    ├── test_master_repo.py
    └── test_daily_task.py
```

### 핵심 인터페이스

```python
# collectors/kis_kr_client.py
from p1_shared.api.kis_api_core import KisApiCore
from datetime import date

class KisKrClient:
    """KIS REST API KR 전용 래퍼. OHLCV + 종목마스터 수집 담당."""

    def __init__(self, api_core: KisApiCore) -> None: ...

    def fetch_daily_ohlcv(
        self,
        stk_cd: str,
        target_date: date,
    ) -> dict | None:
        """
        특정 종목의 target_date 일봉 데이터를 수집.

        ⚠️ KIS API 파라미터 제약조건:
           KIS API는 `adj_price='1'`이 원본(Raw) 주가, `adj_price='0'`이 수정(Adjusted) 주가입니다. (Kiwoom과 반대)
           T-002에서는 Raw(원본) 시세만 수집하므로 반드시 `adj_price='1'`로 요청을 전송해야 합니다.

        ⚠️ KIS `start_date` 무시 특이동작:
           end_date=target_date로 요청 후 응답에서 target_date 행만 필터링.

        Returns:
            dict: {"stk_cd", "dt", "open", "high", "low", "close", "volume"} 또는
            None: 해당 날짜 데이터 없음 (휴장일, 상장 전 등)
        Raises:
            KisApiError: API 오류 시
        """
        ...

    def fetch_stock_master(self) -> list[dict]:
        """
        KIS 마스터 파일(ZIP)을 직접 다운로드하여 KOSPI 및 KOSDAQ 상장 종목 마스터 수집.

        수집 소스:
          - KOSPI: https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip
          - KOSDAQ: https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip

        파싱 및 정규화 규칙:
          - 메모리 상에서 zip 압축 해제 후 cp949 인코딩으로 각 라인 파싱.
          - 단축코드: rf1[0:9].strip()의 마지막 6자리 숫자만 추출하여 stk_cd로 정규화 (예: 'A005930' -> '005930')
          - 종목명: KOSPI는 rf1[21:].strip(), KOSDAQ은 rf1[21:].strip()으로 추출
          - 상장일자: KOSPI는 Part2의 50번째 컬럼(8바이트), KOSDAQ은 45번째 컬럼(8바이트)에서 추출하여 YYYY-MM-DD date 객체 또는 string으로 변환
          - 상장주수: KOSPI는 51번째 컬럼(15바이트), KOSDAQ은 46번째 컬럼(15바이트)에서 추출.
                    특히 KOSDAQ의 경우 상장주수 단위가 '천주'이므로 반드시 1,000을 곱하여 실제 주식수 단위로 저장.

        Returns:
            list[dict]: [{"stk_cd", "stk_nm", "market", "is_active", "listed_dt", "listed_shares"}, ...]
        """
        ...


# repositories/ohlcv_repo.py
class OhlcvRepo:
    def __init__(self, pool: DbConnectionPool) -> None: ...

    def upsert_daily_ohlcv(self, records: list[dict]) -> int:
        """
        daily_ohlcv에 bulk upsert. (stk_cd, dt) ON CONFLICT DO UPDATE.

        Args:
            records: [{"stk_cd", "dt", "open", "high", "low", "close", "volume"}, ...]
        Returns:
            int: upserted 행 수
        """
        ...

    def get_latest_date(self, stk_cd: str) -> date | None:
        """특정 종목의 가장 최근 수집일 반환. 데이터 없으면 None."""
        ...

    def record_gap(self, stk_cd: str, target_date: date, reason: str) -> None:
        """
        수집 실패 종목을 system_milestones 또는 별도 gap 테이블에 기록.
        다음 실행 시 자동 재시도를 위한 추적 목적.
        """
        ...


# repositories/master_repo.py
class MasterRepo:
    def __init__(self, pool: DbConnectionPool) -> None: ...

    def upsert_stock_info(self, records: list[dict]) -> int:
        """
        stock_info에 upsert. PK: stk_cd, ON CONFLICT DO UPDATE.

        Args:
            records: [{"stk_cd", "stk_nm", "market", "is_active", "listed_dt", "listed_shares"}, ...]
        Returns:
            int: upserted 행 수
        """
        ...

    def get_all_active_stocks(self) -> list[dict]:
        """is_active=True인 종목 전체 반환."""
        ...


# tasks/daily_task.py
from datetime import date

class DailyTask:
    def __init__(
        self,
        kis_client: KisKrClient,
        ohlcv_repo: OhlcvRepo,
        master_repo: MasterRepo,
    ) -> None: ...

    def run(self, target_date: date) -> dict:
        """
        일일 수집 실행. 순서: 종목마스터 갱신 → OHLCV 수집.

        Returns:
            dict: {"collected": int, "failed": int, "skipped": int}
        """
        ...
```

---

## § 3. 기존 기능 보존

해당 없음 (신규 구현 Task)

---

## § 4. 테스트 케이스

> **구현 Agent에게**: 아래 테스트 케이스를 먼저 코드로 작성한 뒤,
> 모든 테스트가 통과하도록 구현하세요. 테스트 통과 = Task 완료.

### 4.1 정상 동작 케이스

```python
# tests/test_kis_kr_client.py

def test_fetch_daily_ohlcv_returns_target_date_row_only(mocker):
    """
    [목적] KIS API 응답에서 target_date에 해당하는 행만 반환하며, 반드시 원본 가격(adj_price='1')을 요청하는지 검증.
    [유도] end_date=target_date, adj_price='1'로 요청 후 응답 리스트에서 필터링하는 로직 구현 유도.
           start_date 무시 대응 및 KIS API 파라미터 규칙 준수 보장.
    """
    mock_core = mocker.MagicMock()
    mock_core.get.return_value = {
        "output2": [
            {"stck_bsop_date": "20260514", "stck_oprc": "70000",
             "stck_hgpr": "71000", "stck_lwpr": "69000",
             "stck_clpr": "70500", "acml_vol": "1000000"},
            {"stck_bsop_date": "20260513", "stck_oprc": "69000",
             "stck_hgpr": "70000", "stck_lwpr": "68000",
             "stck_clpr": "69500", "acml_vol": "900000"},
        ]
    }
    client = KisKrClient(api_core=mock_core)
    result = client.fetch_daily_ohlcv("005930", date(2026, 5, 14))

    assert result is not None
    assert result["dt"] == date(2026, 5, 14)
    assert result["stk_cd"] == "005930"
    assert result["close"] == 70500
    assert result["volume"] == 1000000

    # KIS API에 원본 주가(adj_price='1')가 전달되었는지 검증
    # fetch_daily_ohlcv 내부에서 api_core.get을 호출할 때 adj_price='1'이 포함되어야 함
    mock_core.get.assert_called_once()
    called_kwargs = mock_core.get.call_args[1]
    assert called_kwargs.get("adj_price") == "1"


def test_fetch_daily_ohlcv_returns_none_when_date_not_in_response(mocker):
    """
    [목적] API 응답에 target_date가 없을 때(휴장일 등) None을 반환하는지 검증.
    [유도] 필터링 결과가 빈 경우 None 반환 처리 구현 유도.
    """
    mock_core = mocker.MagicMock()
    mock_core.get.return_value = {
        "output2": [
            {"stck_bsop_date": "20260513", "stck_oprc": "69000",
             "stck_hgpr": "70000", "stck_lwpr": "68000",
             "stck_clpr": "69500", "acml_vol": "900000"},
        ]
    }
    client = KisKrClient(api_core=mock_core)
    result = client.fetch_daily_ohlcv("005930", date(2026, 5, 14))

    assert result is None


def test_fetch_stock_master_downloads_and_parses_mst(mocker):
    """
    [목적] KIS 마스터 ZIP 파일을 다운로드하여 단축코드, 종목명, 상장일자, 상장주식을 올바르게 파싱 및 정규화하는지 검증.
    [유도] urllib.request.urlretrieve 또는 requests.get을 mocking하여 가상의 ZIP 데이터를 제공하고,
           KOSDAQ 종목의 경우 상장주수에 1000을 정상 곱하는지 검증.
    """
    # urllib 또는 HTTP Client 모의 객체 설정
    mock_retrieve = mocker.patch("urllib.request.urlretrieve")
    mock_zip = mocker.patch("zipfile.ZipFile")
    
    # KOSPI / KOSDAQ 파싱을 위한 dummy mst 내용 모의 설정
    # (실제 구현 시 zipfile.ZipFile을 mocking하여 open()이 CP949로 인코딩된 스트링을 반환하도록 유도)
    client = KisKrClient(api_core=mocker.MagicMock())
    
    # 이 테스트는 fetch_stock_master()가 정상적으로 다운로드, 압축 해제, 라인 파싱을 수행하여
    # 리스트에 KOSPI와 KOSDAQ 종목 정보를 누적하는지 검증합니다.
    pass


# tests/test_ohlcv_repo.py

def test_upsert_daily_ohlcv_inserts_new_records(mocker):
    """
    [목적] 신규 레코드가 daily_ohlcv에 삽입되고 행 수를 반환하는지 검증.
    [유도] DbConnectionPool.get_cursor() 사용 + INSERT ON CONFLICT DO UPDATE 구현 유도.
    """
    from contextlib import contextmanager
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 2

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    records = [
        {"stk_cd": "005930", "dt": date(2026, 5, 14),
         "open": 70000, "high": 71000, "low": 69000,
         "close": 70500, "volume": 1000000},
        {"stk_cd": "000660", "dt": date(2026, 5, 14),
         "open": 180000, "high": 182000, "low": 178000,
         "close": 181000, "volume": 500000},
    ]
    count = repo.upsert_daily_ohlcv(records)

    assert count == 2
    mock_cursor.executemany.assert_called_once()


def test_get_latest_date_returns_most_recent_date(mocker):
    """
    [목적] get_latest_date()가 특정 종목의 가장 최근 수집일을 반환하는지 검증.
    [유도] SELECT MAX(dt) FROM daily_ohlcv WHERE stk_cd=%s 쿼리 구현 유도.
    """
    from contextlib import contextmanager
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = (date(2026, 5, 13),)

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    result = repo.get_latest_date("005930")

    assert result == date(2026, 5, 13)


# tests/test_master_repo.py

def test_upsert_stock_info_returns_row_count(mocker):
    """
    [목적] 종목 마스터 upsert 후 처리된 행 수를 반환하는지 검증.
    [유도] INSERT INTO stock_info ON CONFLICT(stk_cd) DO UPDATE 구현 유도.
    """
    from contextlib import contextmanager
    mock_cursor = mocker.MagicMock()
    mock_cursor.rowcount = 3

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = MasterRepo(pool=mock_pool)
    records = [
        {"stk_cd": "005930", "stk_nm": "삼성전자",
         "market": "KOSPI", "is_active": True, "listed_dt": date(1975, 6, 11)},
    ]
    count = repo.upsert_stock_info(records)
    assert count == 3


def test_get_all_active_stocks_returns_only_active(mocker):
    """
    [목적] get_all_active_stocks()가 is_active=True인 종목만 반환하는지 검증.
    [유도] WHERE is_active = TRUE 조건 구현 유도.
    """
    from contextlib import contextmanager
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchall.return_value = [
        ("005930", "삼성전자", "KOSPI", True),
        ("000660", "SK하이닉스", "KOSPI", True),
    ]

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = MasterRepo(pool=mock_pool)
    stocks = repo.get_all_active_stocks()

    assert len(stocks) == 2
    assert all(s["is_active"] for s in stocks)


# tests/test_daily_task.py

def test_daily_task_run_updates_master_before_ohlcv(mocker):
    """
    [목적] DailyTask.run()이 종목마스터 갱신 → OHLCV 수집 순서를 보장하는지 검증.
    [유도] PRD §5.1: "팩터 → OHLCV 순서 보장 로직" 준수. 종목마스터가 선행해야
           get_all_active_stocks()로 수집 대상을 확정할 수 있음.
    """
    call_order = []

    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.side_effect = lambda: call_order.append("master") or []
    mock_kis.fetch_daily_ohlcv.side_effect = lambda *a, **kw: call_order.append("ohlcv") or None

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = []

    task = DailyTask(
        kis_client=mock_kis,
        ohlcv_repo=mock_ohlcv_repo,
        master_repo=mock_master_repo,
    )
    task.run(target_date=date(2026, 5, 14))

    assert call_order[0] == "master"


def test_daily_task_run_returns_summary_dict(mocker):
    """
    [목적] run() 결과가 collected/failed/skipped 키를 포함한 dict인지 검증.
    [유도] 수집 결과를 구조화된 형태로 반환하여 로깅 및 모니터링에 활용.
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930"}, {"stk_cd": "000660"}
    ]
    mock_kis.fetch_daily_ohlcv.return_value = {
        "stk_cd": "005930", "dt": date(2026, 5, 14),
        "open": 70000, "high": 71000, "low": 69000,
        "close": 70500, "volume": 1000000
    }

    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 14))

    assert "collected" in result
    assert "failed" in result
    assert "skipped" in result
    assert isinstance(result["collected"], int)
```

### 4.2 경계값 케이스

```python
def test_upsert_daily_ohlcv_with_empty_list_returns_zero(mocker):
    """
    [목적] 빈 리스트 입력 시 0을 반환하고 DB 쿼리를 실행하지 않는지 검증.
    [유도] 불필요한 빈 쿼리 방지 로직 구현 유도.
    """
    mock_pool = mocker.MagicMock()
    repo = OhlcvRepo(pool=mock_pool)
    result = repo.upsert_daily_ohlcv([])

    assert result == 0
    mock_pool.get_cursor.assert_not_called()


def test_get_latest_date_returns_none_for_new_stock(mocker):
    """
    [목적] 한 번도 수집된 적 없는 종목의 get_latest_date()가 None을 반환하는지 검증.
    [유도] fetchone()이 (None,)을 반환하는 경우 None 반환 처리 구현 유도.
    """
    from contextlib import contextmanager
    mock_cursor = mocker.MagicMock()
    mock_cursor.fetchone.return_value = (None,)

    @contextmanager
    def fake_cursor():
        yield mock_cursor

    mock_pool = mocker.MagicMock()
    mock_pool.get_cursor.return_value = fake_cursor()

    repo = OhlcvRepo(pool=mock_pool)
    result = repo.get_latest_date("999999")

    assert result is None


def test_daily_task_records_gap_when_fetch_returns_none(mocker):
    """
    [목적] fetch_daily_ohlcv()가 None을 반환한 종목이 gap으로 기록되는지 검증.
    [유도] 수집 실패 → ohlcv_repo.record_gap() 호출 구현 유도.
           PRD F-01: "수집 실패 종목을 gap 목록으로 별도 기록"
    """
    mock_kis = mocker.MagicMock()
    mock_kis.fetch_stock_master.return_value = []
    mock_kis.fetch_daily_ohlcv.return_value = None  # 수집 실패

    mock_ohlcv_repo = mocker.MagicMock()
    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [{"stk_cd": "005930"}]

    task = DailyTask(mock_kis, mock_ohlcv_repo, mock_master_repo)
    result = task.run(date(2026, 5, 14))

    mock_ohlcv_repo.record_gap.assert_called_once_with(
        "005930", date(2026, 5, 14), mocker.ANY
    )
    assert result["failed"] == 1
```

### 4.3 예외/오류 처리 케이스

```python
def test_fetch_daily_ohlcv_raises_kis_api_error_on_api_failure(mocker):
    """
    [목적] KIS API 오류 시 KisApiError(또는 원본 예외)가 전파되는지 검증.
    [유도] 광범위한 except Exception 대신 구체적 예외 처리 구현 유도.
    """
    import pytest
    mock_core = mocker.MagicMock()
    mock_core.get.side_effect = Exception("API 서버 오류")

    client = KisKrClient(api_core=mock_core)
    with pytest.raises(Exception):
        client.fetch_daily_ohlcv("005930", date(2026, 5, 14))


def test_stocks_endpoint_returns_200_with_stock_list(mocker):
    """
    [목적] GET /api/data/stocks 응답이 200과 종목 목록을 반환하는지 검증.
    [유도] routers/data.py에 /api/data/stocks GET 엔드포인트 + MasterRepo 의존성 주입 구현 유도.
    """
    from fastapi.testclient import TestClient

    mock_master_repo = mocker.MagicMock()
    mock_master_repo.get_all_active_stocks.return_value = [
        {"stk_cd": "005930", "stk_nm": "삼성전자",
         "market": "KOSPI", "is_active": True, "listed_dt": "1975-06-11"},
    ]

    from main import app
    # DI override (FastAPI dependency_overrides 사용)
    from routers.data import get_master_repo
    app.dependency_overrides[get_master_repo] = lambda: mock_master_repo

    client = TestClient(app)
    response = client.get("/api/data/stocks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["stk_cd"] == "005930"

    app.dependency_overrides.clear()
```

### 테스트 케이스 요약

| # | 테스트명 | 유형 | 검증 내용 |
|---|---|---|---|
| 1 | `test_fetch_daily_ohlcv_returns_target_date_row_only` | 정상 | KIS start_date 무시 → target_date 필터링 |
| 2 | `test_fetch_daily_ohlcv_returns_none_when_date_not_in_response` | 정상 | 응답에 날짜 없으면 None 반환 |
| 3 | `test_upsert_daily_ohlcv_inserts_new_records` | 정상 | bulk upsert + 행 수 반환 |
| 4 | `test_get_latest_date_returns_most_recent_date` | 정상 | MAX(dt) 조회 |
| 5 | `test_upsert_stock_info_returns_row_count` | 정상 | 종목마스터 upsert 행 수 |
| 6 | `test_get_all_active_stocks_returns_only_active` | 정상 | is_active=True 필터 |
| 7 | `test_daily_task_run_updates_master_before_ohlcv` | 정상 | 종목마스터 → OHLCV 수집 순서 보장 |
| 8 | `test_daily_task_run_returns_summary_dict` | 정상 | collected/failed/skipped 요약 반환 |
| 9 | `test_upsert_daily_ohlcv_with_empty_list_returns_zero` | 경계값 | 빈 입력 → DB 쿼리 미실행 |
| 10 | `test_get_latest_date_returns_none_for_new_stock` | 경계값 | 신규 종목 최신일 None 반환 |
| 11 | `test_daily_task_records_gap_when_fetch_returns_none` | 경계값 | 수집 실패 → gap 기록 |
| 12 | `test_fetch_daily_ohlcv_raises_kis_api_error_on_api_failure` | 예외 | API 오류 예외 전파 |
| 13 | `test_stocks_endpoint_returns_200_with_stock_list` | 통합 | `/api/data/stocks` 200 응답 |

**총 13개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **KIS API `start_date` 무시**: PRD §3.1 F-02 주의사항 — `end_date=target_date`로 설정 후 응답 리스트에서 `stck_bsop_date == target_date.strftime("%Y%m%d")` 행만 필터링. 원본 `kdms_origin/collectors/kis_rest.py` 페이지네이션 로직 참조.
- **수정주가 저장 금지**: `daily_ohlcv`에는 raw(미수정) 데이터만 저장합니다. KIS API 호출 시 반드시 `adj_price='1'`로 원본(Raw) 가격을 요청하도록 해야 합니다. (`adj_price='0'`은 수정주가이며, 수정주가 저장 테이블(`daily_ohlcv_adjusted`) 개설 및 CTE 기반 최근 N일 배치 갱신 작업은 T-003(수정계수 계산 및 저장) 단계에서 구현합니다.)
- **gap 기록 테이블**: `system_milestones` 또는 전용 `collection_gaps` 테이블 구현 Agent 판단에 위임. 단, `ohlcv_repo.record_gap(stk_cd, date, reason)` 인터페이스는 위에 정의된 대로 유지.
- **FastAPI 의존성 주입 패턴**: `routers/data.py`의 `get_master_repo()`를 Depends로 주입. `app.dependency_overrides`로 테스트에서 Mock 교체.
- **p1_shared 참조**:
  - `pjt_wiki/p1_wiki/interfaces/db_connection_pool.md` — `get_cursor()` context manager 패턴
  - KisApiCore import: `from p1_shared.api.kis_api_core import KisApiCore`
- **원본 참조**: `kdms_origin/tasks/daily_task.py` → `sync_factors_and_prices()` 수집 순서 로직 보존

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 13개 전체 통과
- [ ] `docker-compose up` 상태에서 `DailyTask.run(today)` 실행 시 로그에 `collected: N` 출력 확인
- [ ] `GET /api/data/stocks` 응답 200, 종목 목록 반환 확인
- [ ] `daily_ohlcv` 테이블에 수정주가가 아닌 raw 데이터만 저장되었는지 확인
- [ ] `docs/p2_kdms/p2_kdms_pjt_tasks.md`의 T-002 상태를 `완료`로 업데이트
- [ ] `docs/p2_kdms/tasks/task-002_walkthrough.md` 작성
