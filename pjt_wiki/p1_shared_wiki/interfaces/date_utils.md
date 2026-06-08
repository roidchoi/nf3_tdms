# 미국 주식시장 영업일 및 공휴일 유틸리티 인터페이스 (date_utils.md)

> **Sub Project**: p1_shared (공통 라이브러리)  
> **마지막 업데이트**: 2026-06-05  
> **타입**: Type B (인터페이스 명세)  
> **물리 파일**: `tdms_core/p1_shared/p1_shared/utils/date_utils.py`

---

## 1. 개요

미국 주식시장(NYSE/NASDAQ)의 공휴일 및 주말 여부를 기반으로 특정 일자가 영업일(Trading Day)인지 판단하고, 범위 내의 영업일 리스트 조회 및 기준 시점 직전의 마지막 영업일을 산출하는 공통 유틸리티 함수군입니다.

---

## 2. 함수 시그니처 및 명세

### 2.1 `is_us_trading_day`

```python
def is_us_trading_day(dt: date) -> bool:
    """
    지정된 날짜가 미국 주식시장 영업일인지 판단합니다.
    
    Args:
        dt (date): 판별 대상 일자
        
    Returns:
        bool: 주말(토, 일) 및 미국 연방 공휴일(holidays.US 기준)이 아니면 True, 그렇지 않으면 False
    """
```

* **동작 세부사항**:
  * 내부적으로 `holidays.US(years=dt.year)` 객체를 캐싱/활용하여 공휴일 테이블을 관리합니다.
  * `dt.weekday()`를 활용하여 5(토요일), 6(일요일)은 즉시 `False`를 반환합니다.

---

### 2.2 `get_us_trading_days`

```python
def get_us_trading_days(start_date: date, end_date: date) -> List[date]:
    """
    지정 범위 내의 모든 미국 주식시장 영업일 리스트를 반환합니다.
    
    Args:
        start_date (date): 시작일 (포함)
        end_date (date): 종료일 (포함)
        
    Returns:
        List[date]: 오름차순 정렬된 영업일(date) 목록
    """
```

---

### 2.3 `last_us_trading_day`

```python
def last_us_trading_day(reference: date) -> date:
    """
    기준일(reference)을 제외한 기준일 직전의 마지막 미국 주식시장 영업일을 구합니다.
    
    Args:
        reference (date): 기준 시점 일자
        
    Returns:
        date: 직전 마지막 미국 영업일
    """
```

* **동작 세부사항**:
  * `reference - timedelta(days=1)`부터 역순으로 루프를 돌면서 `is_us_trading_day(curr)`이 `True`인 첫 번째 날짜를 반환합니다.
