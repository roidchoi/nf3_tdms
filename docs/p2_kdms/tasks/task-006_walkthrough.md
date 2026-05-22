# T-006 시가총액 수집 파이프라인 및 스케줄러 자동화 완료 보고

본 문서에서는 P2 KDMS 프로젝트의 **시가총액 수집 파이프라인 구축 및 비동기 스케줄러 통합(T-006)** 구현 내용을 요약합니다.

---

## 1. 구현 요약

전체 아키텍처는 한국거래소(KRX) 웹스크래핑을 전면 배제하고, KIS API 및 공공데이터포털(금융위원회 주식시세정보 API)을 병용하는 하이브리드 수집 전략을 탑재하였습니다.

### 💡 주요 기능별 구현 내역

1. **공공데이터포털 시세 API 수집 클라이언트 (`PubDataClient`)**
   - [pub_data_client.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/collectors/pub_data_client.py)
   - 일반 인증키를 사용해 특정 날짜(`basDt`)의 전 종목 종가, 시가총액, 거래량, 거래대금, 상장주식수를 일괄 조회(5,000건)합니다.
   - 단축코드 정규화(예: `A005930` -> `005930`)와 예외 처리를 정교하게 지원합니다.

2. **시가총액 데이터베이스 레포지토리 (`MarketCapRepo`)**
   - [market_cap_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/market_cap_repo.py)
   - `psycopg2.extras.execute_values`를 통한 벌크 UPSERT 연산으로 `daily_market_cap` 테이블에 빠르게 적재합니다.
   - `trading_calendar` 테이블을 대조하여 데이터가 누락된 과거 영업일을 오름차순으로 역산합니다.

3. **데일리 태스크 연동 (`DailyTask`)**
   - [daily_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py)
   - 매일 KIS OpenAPI로부터 다운로드받은 상장종목 마스터(`listed_shares`)와 당일 수집된 종가(`close`)를 곱해 일별 시가총액을 정밀 역산하며, 수집 완료 시 벌크 적재를 실행합니다.

4. **과거 시가총액 백필 자동화 (`run_backfill_market_cap`)**
   - [backfill_task.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py)
   - 지정된 범위 내의 누락 영업일을 자동 감지하고, 공공데이터 API를 통해 순차적(트래픽 분산용 0.5초 딜레이 포함)으로 가져와 데이터를 보관합니다.
   - 전역 상태 객체(`job_statuses`)와 연동하여 진척도, 현재 단계(Phase), ETA 정보 등을 실시간 갱신합니다.

5. **비동기 스케줄러 (`AsyncIOScheduler`) 기동 및 어드민 연동**
   - [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py) 및 [admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py)
   - FastAPI lifespan 이벤트를 활용해 서울 시간대 기준 `AsyncIOScheduler`를 가동하고 Cron 스케줄 3종을 등록합니다.
     - **평일 17:00 KST**: 데일리 시세 & 시가총액 수집
     - **매일 19:00 KST**: 분기 재무 데이터 갱신
     - **매주 토요일 03:00 KST**: 분봉 데이터 백필
   - 수동 조작 및 상태 관찰용 어드민 라우터 API(`POST /tasks/{task_id}/run`, `GET /tasks/status`)를 바인딩하여 무중단 배치 조작 환경을 완성하였습니다.

---

## 2. 코드 변경 사항 (Diffs)

### [NEW] collectors/pub_data_client.py
```python
# 공공데이터 API 클라이언트 구현
```

### [NEW] repositories/market_cap_repo.py
```python
# 시가총액 저장소 구현
```

### [NEW] routers/admin.py
```python
# 어드민 태스크 제어 API 라우터 구현
```

---

## 3. 테스트 및 검증 결과

테스트 스위트 [test_market_cap_scheduler.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_market_cap_scheduler.py)를 생성하여 다음 6가지의 핵심 시나리오를 검증하였습니다:
1. `test_pub_data_client_fetch_market_cap_success` — 성공적인 API 파싱 및 단축코드 정규화
2. `test_pub_data_client_handles_api_error` — HTTP 500 등 API 예외 대응 및 빈 결과 반환
3. `test_market_cap_repo_upsert_stores_properly` — 벌크 업서트 데이터베이스 트랜잭션 수행
4. `test_daily_task_calculates_and_stores_market_cap` — 데일리 시세 수집 후 시가총액 자동 계산/저장
5. `test_backfill_market_cap_runs_and_updates_status` — 진척율 관리 및 과거 영업일 감지 백필 프로세스 작동
6. `test_admin_run_task_triggers_scheduler_job` — 어드민 라우터를 통한 즉시 실행(1회성 date 트리거) 스케줄 추가 검증

### 🧪 pytest 실행 결과 (All Green)
```bash
$ PYTHONPATH=tdms_core/p1_shared:tdms_core/p2_kdms:tdms_core pytest tdms_core/p2_kdms/tests -v
...
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_pub_data_client_fetch_market_cap_success PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_pub_data_client_handles_api_error PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_market_cap_repo_upsert_stores_properly PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_daily_task_calculates_and_stores_market_cap PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_backfill_market_cap_runs_and_updates_status PASSED
tdms_core/p2_kdms/tests/test_market_cap_scheduler.py::test_admin_run_task_triggers_scheduler_job PASSED
...
============================== 56 passed in 1.45s ==============================
```
기존에 `as_of` 파라미터 불일치로 실패했던 1개 테스트 케이스까지 포함하여 **전체 56개 테스트 케이스가 무결하게 통과(All Green)**함을 검증하였습니다.
