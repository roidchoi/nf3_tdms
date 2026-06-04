# Walkthrough - USDMS Health/Admin API, Auditors, and Live Logs Completion (T-007)

T-007 헬스·어드민 API 구축, Auditors 엔진 3종 마이그레이션, WebSocket 실시간 로그 전송 기능 확장, 그리고 통합 시스템 진단 도구 개발을 완료하였습니다. FastAPI의 `dependency_overrides`를 활용한 단위 및 격리 통합 테스트(Tier 1 + Tier 2)를 설계하여 마감 시각 조건별 데이터 최신성 판정, 거래정지 및 블랙리스트를 제외한 실질 누락율 산출, 재무/지표/수정주가 감사 정합성을 정밀 검증하였습니다.

---

## 구현 파일 목록 및 역할

1. **[health.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/health.py)**:
   - 미국 영업일 캘린더 기준 최신 영업일 수집 완료율을 검증하는 `/freshness` 구현. KST 07:00 이전/이후 분기점 판정 포함.
   - 거래정지(vol=0) 및 블랙리스트를 제외하여 실질 누락율을 산출하는 `/gaps` 구현.
   - 차단 상태인 종목들의 CIK 및 사유 코드를 반환하는 `/blacklist` 구현.

2. **[admin.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/routers/admin.py)**:
   - APIRouter 프리픽스를 `/api/admin`으로 통합 및 조정.
   - 최근 10건의 수집/백필 실행 이력 리포트 JSON 파일 목록을 조회하는 `/tasks/status` 구현.
   - APScheduler의 크론 설정 및 실행 정보를 동적으로 조회하고 수정(reschedule)하는 `/schedules` (GET/PUT) 구현.
   - tail -f 방식의 비동기 파일 폴링을 통해 최신 daily_routine 로그 파일을 실시간 중계하는 WebSocket `/ws/logs` 구현.

3. **[financial_auditor.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/auditors/financial_auditor.py)**:
   - 자산 = 부채 + 자본 회계 항등식 검증(허용 오차 0.1%), 주요 재무 필드 Null 값 발생율, 그리고 공시연도-회계연도 간 2년 초과 이격 이력을 검사하는 재무 감사 엔진 이식 완료.

4. **[metric_auditor.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/auditors/metric_auditor.py)**:
   - ROE 역산 오차(1% 초과) 및 PE 비율 1만 배 초과/미만 아웃라이어를 추출하는 지표 감사 엔진 이식 완료.

5. **[price_auditor.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/auditors/price_auditor.py)**:
   - KIS API 해외 주식 일봉 시세와 로컬 누적수정계수 적용 가격을 대조하는 수정주가 감사 엔진 이식 완료. KIS 입력 형식에 맞춰 하이픈 없는 날짜 전처리 포맷팅 처리.

6. **[run_diagnostics.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/ops/run_diagnostics.py)**:
   - 세 가지 감사 결과(재무, 지표, 수정주가)와 최신 수집 데이터 커버리지를 일괄 검사하고 터미널에 요약 보고하는 통합 시스템 진단 CLI 스크립트 구현.

7. **[main.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/main.py)**:
   - `health_router`를 새롭게 등록하고, lifespan 내에서 APScheduler 객체를 `app.state.scheduler`로 등록하여 동적 스케줄링 API가 획득할 수 있도록 바인딩 반영.

8. **[price_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/price_repo.py) & [blacklist_repo.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/repositories/blacklist_repo.py)**:
   - 헬스 API가 필요로 하는 일봉 데이터 개수 조회 및 차단 블랙리스트 상세 조회를 지원하는 쿼리 헬퍼 메서드(`get_daily_price_count_for_date`, `get_collect_targets_for_date`, `get_blocked_stocks`) 구현 및 통합.

9. **[test_health_auditors.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p3_usdms/tests/test_health_auditors.py)**:
   - FastAPI `app.dependency_overrides`를 사용해 테스트 클라이언트 의존성을 완벽하게 모킹 격리하고, 예외 처리를 디깅할 수 있도록 구성한 TDD 검증 코드 작성.

---

## 주요 설계 및 기술적 결정

* **KST 07:00 미국 시장 수집 마감 분기점 판정**:
  - 한국 시차(KST) 및 미국 현지 시장 마감 시간을 고려해, 오전 7시 이전에 조회할 경우 전영업일 기준 95% 이상을 GREEN 조건으로 충족시키고, 오전 7시 이후에는 당일 수집 커버리지가 95% 이상이어야 수집 완료(GREEN/YELLOW)로 판정하는 유연한 임계치 필터를 설계하였습니다.
* **거래정지 및 블랙리스트 제외를 통한 실질 누락율 산출**:
  - 누락된 일봉 데이터 갭 중 거래량이 0(거래정지)인 종목과 수집 장애가 기록되어 `us_collection_blacklist`에 차단 등록된 종목은 분모(수집 대상 모수) 및 누락 계산에서 전면 제외하여 인프라성 장애나 특수 거래 상태로 인한 오탐지를 방지하였습니다.
* **FastAPI dependency_overrides를 통한 독립 테스트 격리**:
  - 테스트 기동 시 lifespan 등에 의해 실제 DB 및 스케줄러가 개입하지 않도록, `app.dependency_overrides` 맵에 모의 레포지토리 및 컨텍스트 풀 매니저(`MagicMock`)를 주입하여 DB 상태와 완전히 무관한 순수 로직 단위 검증을 보장하였습니다.
* **tail -f 방식의 WebSocket 로그 스트리밍**:
  - WebSocket 연결 즉시 기존 daily_routine 로그의 최신 100줄을 먼저 제공하고, 파일 객체의 현재 스트림 끝 지점(`SEEK_END`)으로 이동한 뒤 `asyncio.sleep` 폴링 주기를 거치며 들어오는 실시간 파일 추가 라인을 스트리밍 전송하도록 설계하였습니다.

---

## 테스트 결과 요약

* **Tier 1 & 2 (단위/모킹 통합 테스트)**:
  - `test_health_freshness_with_high_coverage_returns_green_status`: **PASSED** (98% 이상 수집 시 GREEN 정상 등급 판정)
  - `test_health_gaps_with_blacklist_and_suspended_stocks_excludes_from_total`: **PASSED** (거래정지/차단 종목 제외 시 유효 수집율 100% 정상 계산)
  - `test_health_freshness_with_yellow_boundary_returns_yellow_status`: **PASSED** (95%~98% 경계값 구간에서 YELLOW 등급 판정)
  - `test_financial_auditor_with_zero_assets_skips_accounting_identity`: **PASSED** (자산 0 데이터 유입 시 DivByZero 방지 및 정상 스킵)
* **Tier 3 (실 DB 통합 테스트)**:
  - `test_financial_auditor_with_real_db_retains_accounting_identity`: **PASSED** (실제 DB의 us_standard_financials 테이블 조회 시 정상적으로 작동하도록 쿼리 및 클래스 호환성 검증)
