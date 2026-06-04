# [P2DEC-001] PIT 재무데이터 버전 관리 전략

> **Sub Project**: p2_kdms
> **Status**: active
> **Date**: 2026-05-26
> **Task**: T-004
> **관련**: `[[p2_kdms_wiki/interfaces/financial_repo.md]]`, `[[p2_kdms_wiki/interfaces/data_api_endpoints.md]]`

---

## 배경

KIS OpenAPI로 수집된 재무제표/비율 데이터는 동일 `stac_yymm`(결산년월)에 대해  
수집 시점(`retrieved_at`)에 따라 값이 달라질 수 있다 (수정 공시, 연결/별도 구분 등).

백테스팅 시 특정 시점에 투자자가 알 수 있었던 데이터만 사용해야 하는 PIT(Point-in-Time) 원칙을 강제해야 한다.

---

## 결정 내용

### ON CONFLICT 사용 금지 → INSERT 전략
- `financial_statements`, `financial_ratios` 테이블에 INSERT 시 ON CONFLICT 없이 **항상 신규 행**을 추가.
- `retrieved_at`(TIMESTAMPTZ)이 자동으로 현재 수집 시각으로 기록되어 **버전 이력이 자연스럽게 누적**.

### PIT 조회: DISTINCT ON (stac_yymm) 패턴
```sql
SELECT DISTINCT ON (stac_yymm) *
FROM financial_statements
WHERE stk_cd = %(stk_cd)s
  AND div_cls_code = %(div_cls_code)s
  AND retrieved_at <= %(as_of_date)s   -- PIT 필터
ORDER BY stac_yymm DESC, retrieved_at DESC;
```
- `DISTINCT ON`은 PostgreSQL 전용 문법으로 각 `stac_yymm`에서 가장 최신 retrieved_at 버전만 선택.

### HISTORICAL_CUTOFF 예외 처리
```python
HISTORICAL_CUTOFF = datetime(2025, 11, 8, 0, 0, tzinfo=KST)
```
- 2025-11-08 이전 시점 조회 시 `retrieved_at` 필터 무력화.
- 이유: 해당 날짜 이전에는 대량 초기 수집만 존재하므로 retrieved_at 필터가 빈 결과를 반환할 수 있음.

---

## 영향 범위
- `repositories/financial_repo.py` Lines 111-188
- `routers/data.py` `GET /api/data/financials`

---

## 대안 검토

| 대안 | 거부 이유 |
|---|---|
| UPSERT (ON CONFLICT DO UPDATE) | 과거 버전 삭제 → PIT 재현 불가 |
| 별도 버전 컬럼 | DISTINCT ON 패턴으로 충분, 추가 컬럼 불필요 |
