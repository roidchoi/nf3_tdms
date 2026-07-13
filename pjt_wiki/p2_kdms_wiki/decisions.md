# Sub Project 기술 의사결정 (decisions.md)

> **Sub Project**: p2_kdms **범위**: 이 Sub Project 내부에만 영향을 미치는 결정 **마지막 업데이트**: 2026-05-27

---

## 사용 지침

전체 시스템에 영향을 미치는 결정은 `parent_wiki/decisions.md`에 기록. 이 파일은 이 Sub Project 내부 결정만 다룬다.

---

<!-- 항목 템플릿 --> <!-- --- id: {SUB}DEC-{N} date: YYYY-MM-DD task: Task-{ID} status: active / superseded / reverted --- ## [{SUB}DEC-{N}] {결정 제목} (Task-{ID}) ### 배경 {왜 이 결정이 필요했는가} ### 결정 내용 {무엇을 결정했는가} ### 영향 범위 - {영향받는 모듈/파일} ### 대안 검토 | 대안 | 거부 이유 | |------|----------| | {대안} | {이유} | ### 관련 링크 - `interfaces.md#{섹션}` (인터페이스 영향) - `parent_wiki/decisions.md#{DEC-ID}` (상위 결정과 연관 시) -->

---

## 의사결정 목록

|ID|제목|Task|상태|
|---|---|---|---|
|[[decisions/dec-001_pit_financial_pattern\|P2DEC-001]]|PIT 재무데이터 버전 관리 전략|T-004|active|
|[[decisions/dec-002_price_adjustment_dual_strategy\|P2DEC-002]]|수정주가 이중 제공 전략 (On-the-fly + 물리 테이블)|T-003|active|
|[[decisions/dec-003_support_alphanumeric_stock_codes\|P2DEC-003]]|한국거래소(KRX) 알파벳 혼용 종목코드 지원을 위한 필터 정책 완화|—|active|
|[[decisions/dec-004_kis_api_throttling_strategy\|P2DEC-004]]|KIS API 안전 마진 속도 제어 및 방어적 시가총액 연산 정책|Task-010|active|
|[[decisions/dec-005_filter_non_equity_instruments\|P2DEC-005]]|비주식형 자산 필터링 정책|—|active|
|[[decisions/dec-006_fallback_listed_shares_mechanism\|P2DEC-006]]|상장주식수 0 처리 예외 복구 메커니즘|—|active|
|[[decisions/dec-007_financial_update_optimization\|P2DEC-007]]|KDMS 재무 업데이트 성능 최적화 전략|—|active|
|[[decisions/dec-008_scheduler_reload_and_logging\|P2DEC-008]]|KDMS 스케줄러 동적 리로드 및 진행률 로깅 개선|—|active|