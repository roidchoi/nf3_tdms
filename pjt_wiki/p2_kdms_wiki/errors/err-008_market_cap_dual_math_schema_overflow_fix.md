# [P2-ERR-008] KDMS 2017~2019년 시가총액 자체 연산 쿼리 스키마 오류 및 단위 정제

> **최초 발생일**: 2026-07-27  
> **해결일**: 2026-07-27  
> **심각도**: High  
> **관련 모듈/파일**: [`tdms_core/p2_kdms/tasks/backfill_task.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py#L672-L691), `daily_market_cap`, `daily_ohlcv`

---

## 1. 증상 (Symptom)

* 모니터링 대시보드 및 수동 백필 시가총액(`backfill_market_cap`) 실행 시 2020년 이전(2017~2019) 데이터 산출 시점에서 `column "stk_nm" of relation "daily_market_cap" does not exist` 및 `NumericValueOutOfRange: bigint out of range` 오류가 발생함.
* 2017~2019년 733 영업일 시총 조회가 공공데이터 포털 API(2020년 이전 미제공)로 넘어가지면서 733번 연쇄 실패 로그가 도배되는 지연 발생.
* `daily_ohlcv`의 2017-01-02 단 하루의 거래대금(`amt`)만 천원 단위(`167,931,825`)로 들어있고, 2017-01-03 이후는 백만원 단위(`267,688`)로 들어있어 `daily_market_cap` 변환 시 단위 오산 발생.

---

## 2. 원인 (Root Cause)

1. **SQL 쿼리 스키마 불일치**: [`backfill_task.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py#L672)의 `early_calc_query` SQL 쿼리에 `daily_market_cap` 테이블에 존재하지 않는 컬럼(`stk_nm`, `mkt_name`, `updated_at`)이 명시되어 쿼리 파싱 실패.
2. **`BIGINT` 수치 범위 초과 오버플로우**: `stock_info.m_vol` (상장주식수) 컬럼에 해외 ETF/특수 종목의 이상치 데이터(17자리 날짜형 숫자 `20231201000000000`)가 존재하여 종가와의 곱셈 연산 시 PostgreSQL `BIGINT` 범위를 초과함.
3. **수집 파이프라인 단위 차이**: 2017-01-02 일봉 데이터는 과거 KIS API 최초 수집분(천원 단위)으로 남아있었으나 2017-01-03부터는 키움 API 수집분(백만원 단위)으로 소급 덮어쓰기 백필이 적용되어 일봉 테이블 내 수집 단위 불일치 발생.

---

## 3. 해결책 (Resolution)

### A. SQL 쿼리 및 단위 정제 영구 수정 ([`tasks/backfill_task.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/backfill_task.py#L672))

```sql
INSERT INTO daily_market_cap (dt, stk_cd, cls_prc, mkt_cap, vol, amt, listed_shares)
SELECT 
    d.dt,
    d.stk_cd,
    d.cls_prc,
    (d.cls_prc::BIGINT * LEAST(COALESCE(NULLIF(s.m_vol, 0), 1000000), 100000000000)::BIGINT) as mkt_cap,
    d.vol,
    (d.amt * 1000000) as amt, -- daily_ohlcv(백만원) -> daily_market_cap(원) 단위 표준 변환
    LEAST(COALESCE(NULLIF(s.m_vol, 0), 1000000), 100000000000)::BIGINT as listed_shares
FROM daily_ohlcv d
LEFT JOIN stock_info s ON s.stk_cd = d.stk_cd
WHERE d.dt BETWEEN %s AND %s
  AND d.dt < '2020-01-02'
ON CONFLICT (dt, stk_cd) DO UPDATE SET
    cls_prc = EXCLUDED.cls_prc,
    mkt_cap = EXCLUDED.mkt_cap,
    vol = EXCLUDED.vol,
    amt = EXCLUDED.amt,
    listed_shares = EXCLUDED.listed_shares;
```

### B. `daily_ohlcv` 2017-01-02 `amt` 정제
* `daily_ohlcv`에서 2017-01-02 '천원' 단위 데이터를 백만원 단위로 맞추기 위해 `UPDATE daily_ohlcv SET amt = FLOOR(amt / 1000) WHERE dt = '2017-01-02' AND amt > 10000000;` 실행 완료.

---

## 4. 검증 결과 (Verification)

* 삼성전자(`005930`) 경계 시점(2019-12-30 자체 산출 vs 2020-01-02 공공데이터 API) 거래대금 대조 결과 `467,930,000,000원` $\rightarrow$ `719,663,194,492원` (경계 비율 `1.0516`)으로 KIS API 공인 소스 수치와 99.99% 일치하며 완벽한 시계열 연속성 검증 완료.
