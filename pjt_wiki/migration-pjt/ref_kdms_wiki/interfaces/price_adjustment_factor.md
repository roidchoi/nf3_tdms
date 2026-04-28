# 인터페이스: 수정주가 계수 패턴 (price_adjustment_factor.md)

> **소스 파일**: `migration_pjt/kdms_origin/collectors/factor_calculator.py`
> **관련 테이블**: `daily_ohlcv`, `price_adjustment_factors`
> **관련 API**: `collectors/kis_rest.py`, `collectors/kiwoom_rest.py`
> **마지막 업데이트**: 2026-04-28

---

## 개요

KDMS/USDMS 공통 설계 철학: API가 제공하는 수정주가를 신뢰하지 않고, **Raw 원본 가격과 수정 계수(Factor)를 분리 저장**하여 필요 시 역산합니다.

---

## 핵심 원칙

1. `daily_ohlcv` → **Raw 원본 가격만 저장** (수정 없음)
2. `price_adjustment_factors` → 주식 분할/배당락 이벤트별 수정 계수 저장
3. 수정주가 = `Raw Close × 해당 시점 이후의 모든 factor_val 곱`

---

## 테이블 스키마

```sql
-- price_adjustment_factors
UNIQUE: (stk_cd, event_dt, price_source)

Fields:
  event_dt      DATE        -- 이벤트 발생일 (액면분할, 배당락 등)
  price_ratio   NUMERIC     -- 주가 수정 승수 (예: 0.1 for 10:1 분할)
  volume_ratio  NUMERIC     -- 거래량 수정 승수 (예: 10.0 for 10:1 분할)
  price_source  VARCHAR     -- 'KIWOOM' 또는 'KIS'
  effective_dt  DATE        -- 이 팩터가 기록된 시점 (PIT 추적용)
```

---

## 수정주가 계산 로직

```python
# collectors/factor_calculator.py 패턴
# 특정 기준일 이전 가격을 오늘 기준으로 수정하려면:
# adjusted_price = raw_price × Π(factor_val for all events after price_date)

# 조회 예시 (DB)
SELECT factor_val
FROM price_adjustment_factors
WHERE stk_cd = '005930'
  AND event_dt > {price_date}  -- 해당 가격 이후 발생한 이벤트만
ORDER BY event_dt ASC;
```

---

## KIS vs Kiwoom 동작 차이

| 항목 | KIS | Kiwoom |
|---|---|---|
| 수정주가 제공 | `adj=1` 파라미터 | 별도 수정주가 API |
| start_date 동작 | **무시됨** (end_date로만 페이지네이션) | 정상 작동 |
| 연속 조회 방식 | end_date를 과거로 이동하며 반복 | 표준 페이지네이션 |

> 참고: `standalone_scripts/check_kis_date_range.py` — KIS API 날짜 범위 동작 진단 스크립트

---

## 신규 프로젝트(p1_kdms) 적용 시 참고

- 두 데이터 소스(KIS/Kiwoom)의 팩터를 각각 별도 레코드로 관리할 것 (`price_source` 컬럼 유지)
- `rebuild_factors_from_kis.py` — KIS 기반 전체 팩터 재구축 참고 스크립트
- [[ref_kdms_wiki/interfaces/db_schema]] 의 `price_adjustment_factors` 스키마 참조
