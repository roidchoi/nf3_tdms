# 인터페이스: PIT 재무 데이터 패턴 (pit_financial_pattern.md)

> **소스 파일**: `migration_pjt/kdms_origin/CLAUDE.md`, `collectors/db_manager.py`
> **관련 테이블**: `financial_statements`, `financial_ratios`
> **마지막 업데이트**: 2026-04-28

---

## 개요

재무 데이터는 시간이 지남에 따라 수정됩니다. 수정된 최신 데이터만 사용하면 백테스팅 시 미래 참조 편향(Look-ahead Bias)이 발생합니다. KDMS는 `retrieved_at` 타임스탬프를 PIT Key로 사용하여 이를 방지합니다.

---

## PIT 조회 패턴

```sql
-- 삼성전자(005930) 2023 Q4 재무제표를 2024-01-15 기준으로 조회
-- (즉, 2024-01-15 시점 투자자가 알 수 있었던 가장 최신 정보)
SELECT *
FROM financial_statements
WHERE stk_cd = '005930'
  AND stac_yymm = '202312'
  AND div_cls_code = '0'
  AND retrieved_at <= '2024-01-15 23:59:59+09'
ORDER BY retrieved_at DESC
LIMIT 1;
```

---

## 핵심 컬럼 설명

| 컬럼 | 타입 | 역할 |
|---|---|---|
| `retrieved_at` | `TIMESTAMPTZ` | **PIT Key** - 이 데이터가 수집된 시점 |
| `stac_yymm` | `VARCHAR(6)` | 회계 기간 (예: `202312` = 2023년 12월) |
| `div_cls_code` | `CHAR(1)` | `'0'` = 연간, `'1'` = 분기 |

---

## 신규 프로젝트(p1_kdms) 적용 시 참고

- `retrieved_at` 컬럼을 **인덱스의 DESC 기준**으로 구성하여 최신 데이터 조회 성능 확보
- 동일 `(stk_cd, stac_yymm, div_cls_code)` 조합에 여러 버전 존재 가능 — 쿼리 시 `ORDER BY retrieved_at DESC LIMIT 1`로 최신 버전 조회
- [[ref_kdms_wiki/interfaces/db_schema]] 의 `financial_statements` 스키마 참조
