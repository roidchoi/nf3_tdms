# 인터페이스: 데이터 감사 엔진 3종 (auditors.md)

> **Sub Project**: p3_usdms  
> **마지막 업데이트**: 2026-06-04 (Task-007)  
> **물리 경로**: 
> - `tdms_core/p3_usdms/auditors/financial_auditor.py`
> - `tdms_core/p3_usdms/auditors/metric_auditor.py`
> - `tdms_core/p3_usdms/auditors/price_auditor.py`
> **상태**: ✅ 완료

---

## 1. 개요
USDMS 데이터 수집 및 가공 파이프라인의 종단적 무결성을 정밀 확인하기 위한 3단계 데이터 감사 엔진의 설계 및 시그니처를 명세합니다.

---

## 2. 엔진별 시그니처 및 사양

### ① 재무 감사 엔진 (`FinancialDiagnostic`)
`us_standard_financials` 테이블을 대상으로 공시 재무제표의 회계 기준 왜곡 여부를 감사하는 엔진입니다.

```python
class FinancialDiagnostic:
    def __init__(self, pool):
        """
        DbConnectionPool 객체를 주입받아 데이터베이스 감사 쿼리를 수행합니다.
        """
        
    def check_accounting_identity(self, sample_limit: int = 1000) -> list[dict]:
        """
        자산 = 부채 + 자본 회계 항등식을 검증합니다.
        오차가 0.1%를 초과하는 실패 케이스 목록을 반환합니다. (자산이 0인 데이터는 분모 오류 방지를 위해 skip 처리)
        """
        
    def check_critical_nulls(self) -> list[dict]:
        """
        핵심 재무 필드의 NULL 발생 비율이 허용 임계치를 초과하는지 검증합니다.
        - total_assets: 임계치 5%
        - revenue: 임계치 10%
        - net_income: 임계치 5%
        GREEN/RED 여부를 반환합니다.
        """
        
    def check_historical_leakage(self) -> list[dict]:
        """
        공시연도(filed_dt.year)와 대상 회계연도(fiscal_year) 차이가 2년을 초과하는 공시 왜곡 대상을 검출합니다.
        """
```

### ② 지표 감사 엔진 (`MetricVerifier`)
`us_daily_valuation` 및 `us_financial_metrics` 가치평가 테이블을 대상으로 데이터 및 산출 산식의 무결성을 검증합니다.

```python
class MetricVerifier:
    def __init__(self, pool):
        """
        DbConnectionPool 객체를 주입받아 지표 감사를 수행합니다.
        """
        
    def verify_roe_logic(self, sample_limit: int = 500) -> list[dict]:
        """
        DB에 수집된 ROE 지표 값과 (Net Income / Total Equity) 직접 계산 값을 정대조합니다.
        오차가 1.0%를 초과하여 Consistency가 깨진 케이스들을 검출하여 반환합니다.
        """
        
    def verify_valuation_logic(self, sample_limit: int = 500) -> list[dict]:
        """
        시가총액이 0 이하이거나 PE 비율이 극단적 아웃라이어(PE > 10000 또는 PE < -10000) 구간에 진입한 이상 데이터를 감지합니다.
        """
```

### ③ 수정주가 감사 엔진 (`PriceReproducer`)
수집한 일봉 종가에 누적수정계수(`us_price_adjustment_factors`)를 직접 적용하여 계산한 가격이 KIS 실제 수정 종가와 부합하는지 정밀 대조합니다.

```python
class PriceReproducer:
    def __init__(self, pool, kis_us_client):
        """
        DbConnectionPool 및 KisUSClient API 객체를 주입받아 동작합니다.
        """
        
    def verify_ticker(self, ticker: str, start_dt: str = None, end_dt: str = None) -> dict:
        """
        특정 티커에 대해 로컬 누적수정계수 보정 종가와 KIS API로부터 수집한 실제 수정 종가를 대조합니다.
        - 기본 오차 임계치: 0.1%
        - NVDA 등 특수 수정 패턴 예외 종목: 2.0%
        - 외부 KIS API 호출 시 하이픈이 없는 'YYYYMMDD' 규격으로 날짜를 자동 변환하여 연동 신뢰성을 보장합니다.
        """
```
