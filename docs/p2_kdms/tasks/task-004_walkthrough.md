# Walkthrough - T-004: PIT Financials Module (KIS)

Point-in-Time (PIT) 기반 재무 제표 및 재무 비율 버전 제어 저장/조회 모듈 구현을 성공적으로 완료하였습니다.

## 1. 구현 요약

### 1) Database Repository (`repositories/financial_repo.py`)
- KIS 7개 재무 API 연동 결과를 저장하고, 이력 보존을 위한 Versioned Row 삽입을 구현했습니다.
- `get_statements_as_of` 및 `get_ratios_as_of` 메소드에 PostgreSQL의 `DISTINCT ON (stac_yymm) ... ORDER BY retrieved_at DESC` 패턴을 적용하여, 특정 PIT 시점(`as_of_date`)의 가장 최신 버전을 정확하게 역산해 조회합니다.
- **과거 데이터 바이패스 세이프가드**: 2025-11-08 이전 시점을 조회하는 쿼리에 대해서는 `retrieved_at` 필터를 자동으로 해제하여, 벌크 적재된 과거 데이터가 유실되지 않고 안전하게 조회되도록 설계했습니다.

### 2) API Client & Utils (`collectors/kis_kr_client.py`, `collectors/utils.py`)
- `balance_sheet`, `income_statement`, `financial_ratio` 등 7가지 KIS OpenAPI 엔드포인트를 wrapping하여 단일 종목 재무 정보를 통합 조회하도록 이식했습니다.
- 레거시 데이터 변환 룰(`DATA_MAPPER`)을 이식하고, 정밀 비교 시 0, 0.0, None을 동일한 공백 상태로 취급하여 변경되지 않은 데이터가 불필요하게 신규 버전 로우로 적재되는 현상을 지능적으로 필터링하도록 설계했습니다.

### 3) Collection Task (`tasks/financial_task.py`)
- `job_statuses` 딕셔너리를 통하여 실시간 진척도(it/s, ETA, progress %, Phase 상태)를 로깅하여 백그라운드 태스크의 가시성을 극대화했습니다.
- `DatabaseManager` 와 `KisREST` 를 p2_kdms 환경에 맞는 신규 API Core 기반으로 어댑터 디자인 패턴을 적용해 레거시 동작과의 문법 호환성을 100% 보전했습니다.

### 4) API Endpoint (`routers/data.py`)
- `GET /api/data/financials` 경로를 추가해 특정 종목의 PIT 재무 상태 및 비율 데이터를 일괄 수집/조회할 수 있는 엔드포인트를 연동하였습니다.

---

## 2. 테스트 결과

`pytest`를 활용하여 총 46개 테스트 케이스를 0.94초 만에 모두 **Green(100% Pass)**으로 성공시켰습니다.

```bash
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1
collected 46 items                                                             

tdms_core/p2_kdms/tests/test_base_repository.py .........                [ 19%]
tdms_core/p2_kdms/tests/test_daily_task.py ....                          [ 28%]
tdms_core/p2_kdms/tests/test_factor_calculator.py ...                    [ 34%]
tdms_core/p2_kdms/tests/test_factor_endpoints.py ...                     [ 41%]
tdms_core/p2_kdms/tests/test_factor_repo.py ...                          [ 47%]
tdms_core/p2_kdms/tests/test_financial_endpoints.py ...                  [ 54%]
tdms_core/p2_kdms/tests/test_financial_repo.py .....                     [ 65%]
tdms_core/p2_kdms/tests/test_financial_task.py ....                      [ 73%]
tdms_core/p2_kdms/tests/test_kis_kr_client.py ....                       [ 82%]
tdms_core/p2_kdms/tests/test_master_repo.py ...                          [ 89%]
tdms_core/p2_kdms/tests/test_ohlcv_repo.py ....                          [ 97%]
tdms_core/p2_kdms/tests/test_ohlcv_repo_adjusted.py .                    [100%]

============================== 46 passed in 0.94s ==============================
```
