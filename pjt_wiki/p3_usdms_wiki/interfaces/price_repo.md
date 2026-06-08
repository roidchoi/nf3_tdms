# 인터페이스: PriceRepo (price_repo.md)

> **파일명**: `tdms_core/p3_usdms/repositories/price_repo.py`  
> **상속 클래스**: `p3_usdms.repositories.base.BaseRepository`  
> **마지막 업데이트**: 2026-06-01 (Task-002-B)  

---

## 1. 개요
미국 주식의 일별 가격 원본 시세(`us_daily_price`) 및 가격 수정계수(`us_price_adjustment_factors`) 데이터베이스 I/O를 전담하는 저장소 계층 인터페이스입니다. TimescaleDB 하이퍼테이블 벌크 성능을 극대화하기 위해 `execute_values`를 적극 활용합니다.

---

## 2. 주요 메서드 시그니처

### `insert_daily_price`
일일 가격 레코드 리스트를 받아 테이블에 bulk insert(업서트)합니다.
```python
def insert_daily_price(self, records: list[dict]) -> None
```
- **동작**: `ON CONFLICT (dt, cik) DO UPDATE` 절을 사용하여 기 존재하는 종가 데이터에 대한 증분 갱신 및 덮어쓰기를 원자적 트랜잭션으로 처리합니다.

### `upsert_price_factors`
계산된 가격 수정계수 목록을 데이터베이스에 업서트합니다.
```python
def upsert_price_factors(self, records: list[dict]) -> None
```
- **동작**: `ON CONFLICT (cik, event_dt) DO UPDATE` 절을 활용해 특정 시점의 수정계수 변동 이력을 무결성하게 갱신합니다.

### `get_daily_prices`
특정 종목의 지정 기간 동안의 원본 일봉 시세를 오름차순으로 조회합니다.
```python
def get_daily_prices(self, cik: str, start_dt: str, end_dt: str) -> list[dict]
```

### `get_price_factors`
특정 종목의 전체 가격 수정계수 이력을 날짜순으로 조회합니다.
```python
def get_price_factors(self, cik: str) -> list[dict]
```
- **반환형**: 데이터베이스 Row 결과를 `RealDictRow`(딕셔너리형) 리스트 형식으로 반환합니다.

### `get_daily_price_count_for_date`
특정 날짜에 수집 완료된 일봉 데이터의 총 개수를 조회합니다.
```python
def get_daily_price_count_for_date(self, dt: date | str) -> int
```

### `get_collect_targets_for_date`
특정 날짜 기준 수집 대상(is_collect_target=True)인 티커 목록을 조회합니다.
```python
def get_collect_targets_for_date(self, dt: date | str) -> list[str]
```

