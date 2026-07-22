# DEC-012: MasterSync 방어적 권한 검증 및 Safety Lock 도입

> **Sub Project**: p3_usdms  
> **날짜**: 2026-07-23  
> **상태**: Accepted  
> **관련 모듈**: `tdms_core/p3_usdms/collectors/master_sync.py`

---

## 1. 배경 및 문제점

- **현상**: 엑손모빌(`XOM`, CIK `0000034088`)을 포함한 74개 정상 상장 대형주가 개발 PC DB에서 단 일회성 배치 실행 시 `is_active = FALSE`, `is_collect_target = FALSE`로 한꺼번에 비활성화되는 오탐(False Positive Delisting)이 발생함.
- **원인**:
  1. SEC EDGAR의 `company_tickers.json` 다운로드 시 일시적 네트워크 딜레이나 롤링 누락으로 CIK가 빠지면 `delisted_candidates`로 전락함.
  2. 2차 검증인 `_verify_batch_authority()`에서 SEC `submissions` API 호출 시 HTTP 429 Rate Limit, 타임아웃, 예외 발생 시 `return {'is_active': False}`로 강제 처리하여, 단 1회의 네트워킹 장애만으로 정상 상장 기업을 상장폐지로 판정함.

---

## 2. 결정 사항

1. **방어적 예외 처리 (Defensive Authority Check)**:
   - HTTP 200이 아닌 응답(429, 503, Timeout, Network Exception) 발생 시 `is_active: None` (검증 보류/보존) 상태를 반환하도록 개편.
   - 오직 **SEC HTTP 404 (SEC에 CIK 미존재)** 일 때만 `is_active: False`로 수용.
2. **대량 상장폐지 방지 임계치 (Safety Lock)**:
   - 단일 동기화 배치에서 상장폐지 후보(`verified_delisted`) 수량이 전체 활성 종목의 **1% (35개 초과)** 발생 시, 대량 상장폐지 락(Safety Lock)을 가동하여 자동 비활성화 쿼리 실행을 중단(Abort)하고 경고 로그를 발생시킴.
3. **블랙리스트 자동 쿨다운 릴리즈 필수 연동**:
   - `UsFinancialRoutine` 기동 및 주간 유지보수 스케줄 시작 시 `BlacklistManager.auto_release_expired_blocks()`를 의무 실행하여 유예기간(1일/7일/30일/60일)이 만료된 차단 종목의 자동 릴리즈를 보장함.

---

## 3. 결과 및 영향

- **네트워크 장애 내구성 확보**: SEC API 서버 과부하나 임시 패킷 유실 시에도 우량 상장 종목이 비활성화되는 리스크 100% 차단.
- **데이터 정합성 원복**: 오탐 비활성화 처리되었던 엑손모빌(`XOM`) 포함 74개 우량 종목이 `is_active=TRUE`, `is_collect_target=TRUE`로 완벽 복구됨.
