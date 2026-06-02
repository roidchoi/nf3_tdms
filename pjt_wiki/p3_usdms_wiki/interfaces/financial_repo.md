# Interface: FinancialRepo

미국 재무 데이터 및 주식 수 변경 이력 테이블의 DB CRUD 및 Upsert를 담당하는 레포지토리 클래스입니다.

> **파일 경로**: `tdms_core/p3_usdms/repositories/financial_repo.py`
> **상속 관계**: `BaseRepository` 상속

---

## 1. 개요
TimescaleDB/PostgreSQL 상의 `us_financial_facts`, `us_standard_financials`, `us_share_history` 세 개의 테이블에 대한 쓰기 및 삭제 오퍼레이션을 수행합니다. 중복 저장 방지를 위한 벌크 교체 및 복합 PK 충돌 시 `ON CONFLICT` 처리 전략이 수립되어 있습니다.

---

## 2. API Reference

### `FinancialRepo.delete_raw_facts_by_cik(cik: str) -> None`
특정 CIK에 저장된 EAV 로우 facts 데이터를 전부 삭제합니다.
- **Parameters**:
  - `cik` (str): 기업 CIK

### `FinancialRepo.insert_financial_facts(records: List[Dict[str, Any]]) -> None`
EAV 로우 facts를 `us_financial_facts` 테이블에 `execute_values`를 사용하여 벌크 인서트합니다.
- **Parameters**:
  - `records` (List[Dict[str, Any]]): 삽입할 EAV 사전 객체 리스트

### `FinancialRepo.upsert_standard_financials(records: List[Dict[str, Any]]) -> None`
표준화 재무 데이터를 `us_standard_financials` 테이블에 벌크 업서트합니다.
- **Conflict Target**: `(cik, report_period, filed_dt)`
- **Parameters**:
  - `records` (List[Dict[str, Any]]): 표준 재무 레코드 리스트

### `FinancialRepo.upsert_share_history(records: List[Dict[str, Any]]) -> None`
주식 수 이력을 `us_share_history` 테이블에 벌크 업서트합니다.
- **Conflict Target**: `(cik, filed_dt)`
- **Parameters**:
  - `records` (List[Dict[str, Any]]): 주식수 이력 레코드 리스트
