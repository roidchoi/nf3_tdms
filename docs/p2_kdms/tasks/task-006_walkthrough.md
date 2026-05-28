# T-006 시가총액 수집 파이프라인, 스케줄러 자동화 및 데이터 파이프라인 안정성 고도화 완료 보고

본 문서에서는 P2 KDMS 프로젝트의 **시가총액 수집 파이프라인 구축 및 비동기 스케줄러 통합(T-006)**의 기능 구현과 이에 따른 **데이터 수집 파이프라인 신뢰성 고도화(휴장일 조기 종료, 팩터 정화 루프 이식, 분봉 일일 수집 통합)** 작업 내용을 요약합니다.

---

## 1. 구현 요약

전체 아키텍처는 한국거래소(KRX) 웹스크래핑을 전면 배제하고, KIS API 및 공공데이터포털(금융위원회 주식시세정보 API)을 병용하는 하이브리드 수집 전략을 탑재하였으며, 무결성과 신뢰성을 위해 3대 데이터 파이프라인 Gap 보완책을 추가 구현하였습니다.

### 💡 주요 기능별 구현 내역

1. **공공데이터포털 시세 API 수집 클라이언트 (`PubDataClient`)**
   - [pub_data_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/pub_data_client.py)
   - 일반 인증키를 사용해 특정 날짜(`basDt`)의 전 종목 종가, 시가총액, 거래량, 거래대금, 상장주식수를 일괄 조회(5,000건)합니다.
   - 단축코드 정규화(예: `A005930` -> `005930`)와 예외 처리를 정교하게 지원합니다.

2. **시가총액 데이터베이스 레포지토리 (`MarketCapRepo`)**
   - [market_cap_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/market_cap_repo.py)
   - `psycopg2.extras.execute_values`를 통한 벌크 UPSERT 연산으로 `daily_market_cap` 테이블에 빠르게 적재합니다.
   - `trading_calendar` 테이블을 대조하여 데이터가 누락된 과거 영업일을 오름차순으로 역산합니다.

3. **데일리 태스크 연동 및 고도화 (`DailyTask`)**
   - [daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py)
   - **휴장일 조기 종료 (Early Exit)**: `is_kr_trading_day` 유틸리티를 적용해 비영업일에 불필요한 KIS API 통신 및 마스터 갱신 작업을 조기 스킵하고 리턴합니다.
   - **팩터 정화 (Clean-up Loop 1 & 2)**:
     - **Loop 1 (이벤트 사후 소멸 보정)**: KIS API 계산결과 팩터 날짜와 기존 DB 팩터 날짜를 45일 범위 정합성이 맞는 경우 비교하여, 사후 정정으로 인해 소멸된 날짜를 DB에서 동적으로 삭제합니다.
     - **Loop 2 (오류 추정 종목 정리)**: 루프 1을 거친 뒤에도 여전히 오차가 잔존하거나 API 오류가 추정되어 맵에 남아있는 종목들의 전체 시세 데이터를 로드하여 재계산(참 팩터 리스트 추출)한 뒤 불필요한 팩터를 완벽히 정리합니다.
   - **분봉 데이터 일일 수집 통합**: 당일 영업일 수집의 마지막 단계로 `_collect_daily_minute_data`를 기동하여, 분기 상위 대상 종목의 당일자 분봉 데이터를 키움 OpenAPI에서 실시간으로 가져와 일일 업서트합니다. (Rate Limit 제어를 위해 0.2초 sleep 딜레이 적용)

4. **과거 시가총액 백필 자동화 (`run_backfill_market_cap`)**
   - [backfill_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py)
   - 지정된 범위 내의 누락 영업일을 자동 감지하고, 공공데이터 API를 통해 순차적(트래픽 분산용 0.5초 딜레이 포함)으로 가져와 데이터를 보관합니다.
   - 전역 상태 객체(`job_statuses`)와 연동하여 진척도, 현재 단계(Phase), ETA 정보 등을 실시간 갱신합니다.

5. **비동기 스케줄러 (`AsyncIOScheduler`) 기동 및 어드민 연동**
   - [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py) 및 [admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py)
   - FastAPI lifespan 이벤트를 활용해 서울 시간대 기준 `AsyncIOScheduler`를 가동하고 스케줄을 자동 기동합니다.
   - **주간 분봉 크론 스케줄러 제거**: 일일 수집으로 이관됨에 따라 매주 토요일 구동되던 크론 등록을 해제하여 리소스를 최적화하였습니다.
   - 수동 조작 및 상태 관찰용 어드민 라우터 API(`POST /tasks/{task_id}/run`, `GET /tasks/status`)를 바인딩하여 무중단 배치 조작 환경을 완성하였습니다.

---

## 2. 주요 코드 변경 사항

### 1) repositories/ohlcv_repo.py
- [ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py)
- `get_minute_target_history`: 특정 분기 및 시장의 분봉 수집 대상 종목 조회.
- `upsert_minute_target_history`: 분기 대상 종목 정보를 `minute_target_history` 테이블에 UPSERT.
- `upsert_minute_ohlcv`: 분봉 데이터의 효율적 대량 업서트를 구현.
- `fetch_ohlcv_for_factor_calc`: 원본 주가와 수정 주가의 병합 데이터를 정밀 조회해 Loop 2 오차 검증 지원.

### 2) repositories/factor_repo.py
- [factor_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/factor_repo.py)
- `get_recent_event_stocks_map`: 최근 N일 이내에 발생한 수정계수 종목 및 날짜 맵 반환.
- `delete_adjustment_factors_by_dates`: 사후 소멸된 불필요 수정계수를 데이터베이스에서 삭제.

### 3) tasks/daily_task.py
- [daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py)
- 휴장일(영업일 여부)을 판별하여 비영업일에는 프로세스를 중단하는 조기 종료 기능 장착.
- 루프 1(이벤트 정정 소멸 감지 및 DB 삭제) 및 루프 2(전체 기간 재검증을 통한 오류 보정)를 순차적으로 실행해 팩터 청소 로직 구체화.
- `_collect_daily_minute_data`를 내장하여 일일 배치 주기의 마지막 단계로 분봉 수집 연동.

---

## 3. 테스트 및 검증 결과

테스트 스위트 [test_market_cap_scheduler.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_market_cap_scheduler.py)에 다음과 같이 신규 고도화 기능 검증을 위한 모의 유닛 테스트 3종을 신설하였습니다:
1. `test_daily_task_early_exit_on_holiday` — 한국 휴장일(주말 등) 입력 시 KIS API 호출을 전면 스킵하고 종료되는지 검증.
2. `test_daily_task_factor_cleanup_and_loop2` — Loop 1의 동적 사후 소멸 날짜 삭제와 Loop 2의 전체 기간 재검증 기반 참 팩터 필터링 및 팩터 삭제 로직 동작 검증.
3. `test_daily_task_collects_minute_data` — 분기 상위 종목 타겟팅을 조회해 Kiwoom OpenAPI 클라이언트를 거쳐 분봉 데이터 수집 및 업서트 수행 흐름 검증.

### 🧪 pytest 실행 결과 (All Green)
```bash
$ PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms pytest tdms_core/p2_kdms/ -v
...
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_daily_task_early_exit_on_holiday PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_daily_task_factor_cleanup_and_loop2 PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_daily_task_collects_minute_data PASSED
...
============================== 59 passed in 1.47s ==============================
```
보완된 스케줄러, 레포지토리 및 일일 수집 파이프라인의 모든 코드가 기존 56건 및 신규 3건을 포함하여 **전체 59개 테스트 케이스가 무결하게 통과(All Green)**함을 검증하였습니다.
