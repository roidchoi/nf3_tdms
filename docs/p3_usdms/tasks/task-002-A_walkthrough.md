# Walkthrough - USDMS Master Ticker Synchronization Core (T-002-A)

미국 시장 데이터 백엔드 구축의 첫걸음인 SEC EDGAR API 연동 및 티커 마스터 동기화 파이프라인(T-002-A)을 성공적으로 구현 및 검증 완료하였습니다.

## 1. 구현 내용 요약

### A. SEC EDGAR API 클라이언트 (`sec_client.py`)
- `company_tickers.json`, `company_tickers_exchange.json`, `submissions`, SEC Daily Index (.idx) 파일 파싱 지원.
- SEC API 규정을 엄격히 준수하는 0.15초 Delay의 Rate Limiting 적용.
- `SEC_USER_AGENT` 누락 시 생성자 단계에서 `ValueError`를 발생시켜 안전한 구동 보장.

### B. 마스터 동기화 엔진 (`master_sync.py`)
- **V2 Primary Ticker Resolution**: Exception Map(구글 FOXA 등 하드오버라이드), Exchange Rank, 특수문자 Purity, Stickiness, Tie-Breaker 규칙을 순서대로 적용하여 CIK 당 1개의 대표 티커 결정.
- **SCD Type 2 이력 관리**: 티커/거래소 변경 시 `us_ticker_history`에 반영하며, 하루 미만의 노이즈 변경 사항은 Transient Noise Deletion 로직으로 제거.
- **yfinance Enrichment**: 멀티스레드 기반 비동기 `ThreadPoolExecutor`와 데드락 방지 전용 `BufferedLogHandler`를 이용해 안전하게 종목의 섹터, 산업, 시가총액, 현재가 등의 메타데이터 보강.
- **Targeting**: 시가총액 35M 미만, 0.8달러 미만 탈락(Retention) 및 50M 이상, 1.0달러 이상 진입(Entry) 규칙 자동 분석.

### C. 마스터 레포지토리 (`master_repo.py`)
- `BaseRepository`를 상속받아 `us_ticker_master`, `us_ticker_history` 테이블에 안전하게 접근하는 데이터 레이어 구현.
- `get_active_tickers()`, `get_collect_targets()`, `get_ticker_history()` 인터페이스 제공.

### D. FastAPI 엔드포인트 (`routers/data.py` & `main.py`)
- `/api/data/tickers` 경로로 활성 종목 및 수집 대상(collect_only 필터)을 조회하는 엔드포인트 추가 및 `lifespan`에 연동.

---

## 2. 테스트 및 검증 결과

### 자동화 테스트 결과
Tier 1, Tier 2, Tier 3 전체 12개 테스트 케이스가 100% 통과(All Green) 하였습니다.

```bash
$ pytest tests/ -v --run-integration

tests/test_base_infra.py::test_env_detector_resolves_local_development_env PASSED
tests/test_base_infra.py::test_db_connection_pool_creates_and_fetches_cursor PASSED
tests/test_base_infra.py::test_startup_validator_passes_all_checks_on_dev PASSED
tests/test_base_infra.py::test_db_manager_shim_provides_compatible_context_cursor PASSED
tests/test_base_infra.py::test_fastapi_lifespan_executes_startup_sequence PASSED
tests/test_base_infra.py::test_config_with_empty_or_missing_env_vars_raises_error PASSED
tests/test_base_infra.py::test_backup_manager_handles_invalid_dest_path_and_logs_error PASSED
tests/test_master_sync.py::test_normalize_exchange_returns_standardized_names PASSED
tests/test_master_sync.py::test_resolve_primary_ticker_prefers_higher_rank_and_purity PASSED
tests/test_master_sync.py::test_sync_daily_inserts_new_listings PASSED
tests/test_master_sync.py::test_sec_client_constructor_raises_value_error_if_user_agent_missing PASSED
tests/test_master_sync.py::test_master_sync_flow_with_real_db PASSED
```

- **Tier 1 & 2 (격리 단위/통합)**: 모킹된 환경에서 예외 처리 및 Diff 로직 검증 완료.
- **Tier 3 (실 DB 통합)**: Docker에 기동 중인 `usdms_timescaledb` 컨테이너(5433 포트)에 연동하여 데이터베이스 물리 이력 작성 및 조회 성공 검증 완료.
