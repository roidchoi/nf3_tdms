# T-008 헬스·어드민 API 및 WebSocket 구현 Walkthrough

T-008 Task에서는 기존 KDMS의 헬스체크 및 어드민 기능을 대폭 보완하여 실질적인 데이터베이스 정합성 확보와 다중 접속자 지원 WebSocket 로그 스트리밍을 제공하는 시스템을 성공적으로 구현 및 검증 완료하였습니다.

## 1. 구현 내용 요약

### 1-1. 데이터 최신성 및 수집 커버리지율 검증 API (`GET /api/health/freshness`)
- **영업일 캘린더 연계**: `trading_calendar` 테이블에서 개장일(`opnd_yn = 'Y'`)을 기반으로 최신 2개 영업일을 도출합니다.
- **적재율 산출**: `stock_info` 기준 현재 활성화된 전체 상장 종목수 대비 최신 영업일에 수집된 일봉(`daily_ohlcv`) 데이터 수집률을 계산합니다.
- **최신성 판정 오탐 방지**: 
  - 장마감(16:00) 이전에는 전 영업일 데이터 수집률이 95% 이상일 경우 `is_daily_fresh = True`로 인정합니다.
  - 장마감 이후에는 당일 데이터가 95% 이상 들어왔을 때 `is_daily_fresh = True`로 판정합니다.
- **분봉 최신성**: 최신 영업일(혹은 장중 전 영업일)의 분봉 데이터 적재 유무를 확인합니다.

### 1-2. 미시적 누락 탐지 정밀화 API (`GET /api/health/gaps`)
- **거래정지 배제**: 일봉상 거래량(`vol == 0`)인 종목은 수집 제외로 간주하고 모수에서 배제합니다.
- **수집 예외 배제**: `daily_ohlcv_gap` 테이블에 수집 갭 사유가 등록된 종목 또한 모수에서 배제합니다.
- **성공률 계산**: `(유효 타겟 - 미시 누락) / 유효 타겟 * 100`으로 실질 수집 성공률을 계산하여 98% 이상을 `GREEN`, 95% 이상 98% 미만을 `WARNING`, 95% 미만을 `CRITICAL` 상태로 정의합니다.

### 1-3. 데이터 정합성 전수 검사 API (`GET /api/health/integrity`)
- **수정주가 역산 공식 검증**: `physical_close != round(raw_close * adj_factor)` (오차 ±0.01 초과)인 데이터 정합성 오류를 전수 검사합니다.
- **변동 제한 위반 검출 및 IPO 예외**: 수정 종가의 하루 등락폭이 ±30.1%를 초과하는 데이터를 검출하되, `stock_info.list_dt`를 조회하여 최초 상장일(IPO) 당일 시세는 검출 대상에서 제외합니다.
- **시가총액 종가 교차 검증**: `daily_ohlcv`와 `daily_market_cap`의 종가(`cls_prc`) 필드가 불일치하는 데이터를 검출합니다.
- **재무제표 짝 누락 검증**: `financial_statements`는 존재하나 `financial_ratios`는 누락된 데이터 불완전 상태를 검출합니다.

### 1-4. 시스템 마일스톤 API (`GET/POST /api/health/milestones`)
- `system_milestones` 테이블을 대상으로 데이터 CRUD 및 조회(UPSERT)를 완결했습니다.

### 1-5. APScheduler 제어 및 WebSocket 실시간 스트리밍
- **스케줄러 상태 제어**: `GET /api/v1/admin/scheduler`를 통해 활성 스케줄 현황을 확인하고, `POST /api/v1/admin/scheduler/{job_id}/toggle?action=pause/resume`을 통해 특정 크론 직무를 정지 및 복구할 수 있습니다.
- **WebSocket 멀티캐스팅**: Pub/Sub 구조의 `LogBroadcaster`를 구현하여 다중 사용자가 동시에 실시간 로그 스트림(`WS /ws/logs`)을 유실 없이 전송받을 수 있도록 개발하였습니다.

---

## 2. 테스트 검증 결과

단위 테스트 및 모의(Mocking) 기반 시나리오 테스트를 작성하여, 총 10개의 테스트 케이스가 성공(All Green)함을 확인하였습니다.

### 2-1. 테스트 결과 내역

```bash
$ conda run -n tdms_p2_env python -m pytest tests/test_health_t008.py tests/test_logs_ws_t008.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1, asyncio-1.4.0
collected 10 items

tests/test_health_t008.py::test_health_freshness_green_when_high_coverage PASSED [ 10%]
tests/test_health_t008.py::test_health_freshness_red_when_stale PASSED   [ 20%]
tests/test_health_t008.py::test_health_gaps_excludes_suspended_stocks_from_rate PASSED [ 30%]
tests/test_health_t008.py::test_health_gaps_warning_when_rate_under_98 PASSED [ 40%]
tests/test_health_t008.py::test_integrity_adjusted_price_mismatch_detection PASSED [ 50%]
tests/test_health_t008.py::test_integrity_price_limit_violation_over_30_percent PASSED [ 60%]
tests/test_health_t008.py::test_integrity_price_limit_excludes_ipo_listing_date PASSED [ 70%]
tests/test_health_t008.py::test_integrity_market_cap_close_mismatch PASSED [ 80%]
tests/test_health_t008.py::test_integrity_financials_missing_ratios_mismatch PASSED [ 90%]
tests/test_logs_ws_t008.py::test_ws_logs_broadcast_to_multiple_clients PASSED [100%]

============================== 10 passed in 1.37s ==============================
```

---

## 3. 관련 파일 링크

- **구현 소스**:
  - [routers/health.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/health.py)
  - [routers/admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py)
  - [utils/log_broadcaster.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/utils/log_broadcaster.py)
  - [repositories/ohlcv_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/ohlcv_repo.py)
  - [repositories/master_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/master_repo.py)
  - [main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/main.py)
- **테스트 소스**:
  - [tests/test_health_t008.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_health_t008.py)
  - [tests/test_logs_ws_t008.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tests/test_logs_ws_t008.py)
