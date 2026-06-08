# Interface: XBRLMapper

미국 주식 회계 표준 필드(US-GAAP) 매핑 및 가감 정규화를 수행하는 매니저 클래스입니다.

> **파일 경로**: `tdms_core/p3_usdms/collectors/xbrl_mapper.py`

---

## 1. 개요
SEC EDGAR raw facts API를 조회한 결과 얻어지는 US-GAAP의 다양하고 불규칙한 원시 태그를 시스템 표준 분석 필드(예: `total_assets`, `revenue` 등)에 매핑합니다.
우선순위(Fallback) 매핑 순서에 입각하여 값이 발견되는 최상위 태그를 사용하며, 자본지출(Capex) 등 비용 데이터에 대해서 부호 정규화를 처리합니다.

---

## 2. API Reference

### `XBRLMapper.map_fact(field: str, facts: List[Dict[str, Any]]) -> Optional[float]`
주어진 단일 기간의 raw facts 풀에서 필드 우선순위/대체 로직을 반영해 표준 값을 추출합니다.

- **Parameters**:
  - `field` (str): 정제하고자 하는 타겟 표준 필드명 (예: `'total_assets'`, `'revenue'`, `'capex'` 등)
  - `facts` (List[Dict[str, Any]]): 해당 회계 기간의 raw facts 목록 (각 팩츠는 `tag` 및 `val` 키를 포함해야 함)
- **Returns**: `Optional[float]` - 표준 필드에 대응하는 최종 수치값 (매핑 실패 시 `None` 반환)

### `XBRLMapper.normalize_sign(field: str, value: float) -> float`
필드별로 부호의 정규화를 처리합니다.

- **Parameters**:
  - `field` (str): 표준 필드명
  - `value` (float): 소스 수치값
- **Returns**: `float` - 정규화된 최종값 (예: capex의 경우 양수 크기로 절대값 변환)
