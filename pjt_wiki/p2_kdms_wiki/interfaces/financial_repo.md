# Interface: FinancialRepo

> **파일**: `tdms_core/p2_kdms/repositories/financial_repo.py`
> **클래스**: `FinancialRepo`
> **Graphify**: God Node #3 (degree=38) — PIT 재무 데이터의 단일 진실 공급원
> **관련**: `[[p2_kdms_wiki/interfaces/ohlcv_repo.md]]`, `[[p2_kdms_wiki/decisions/dec-001_pit_financial_pattern.md]]`, `[[p2_kdms_wiki/codebase_map.md]]`

---

## 클래스 상수 (모듈 수준)

```python
KST = ZoneInfo("Asia/Seoul")
HISTORICAL_CUTOFF = datetime(2025, 11, 8, 0, 0, tzinfo=KST)
```

> ⚠️ **중요**: `HISTORICAL_CUTOFF` 이전 시점 쿼리에서는 `retrieved_at` 필터를 무력화 (데이터 누락 방지).  
> 이 커트오프는 초기 대량 수집일(2025-11-08)에 대응하는 하드코딩된 값임.

---

## 클래스 시그니처

```python
class FinancialRepo:
    def __init__(self, pool: DbConnectionPool) -> None
```

---

## 메서드 목록

### `get_latest_statement(stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]`
- **위치**: Line 23
- **쿼리**: `SELECT * FROM financial_statements ... ORDER BY retrieved_at DESC LIMIT 1`
- **반환**: 딕셔너리 or `None`

---

### `get_latest_ratio(stk_cd: str, stac_yymm: str, div_cls_code: str) -> Optional[Dict[str, Any]]`
- **위치**: Line 38
- **쿼리**: `SELECT * FROM financial_ratios ... ORDER BY retrieved_at DESC LIMIT 1`
- **반환**: 딕셔너리 or `None`

---

### `insert_statements(statements: List[Dict[str, Any]]) -> int`
- **위치**: Line 53
- **테이블**: `financial_statements`
- **전략**: ON CONFLICT 없이 항상 신규 INSERT → retrieved_at 별 버전 누적 (PIT 원칙)
- **컬럼**: `stk_cd`, `stac_yymm`, `div_cls_code`, `cras`, `fxas`, `total_aset`, `flow_lblt`, `fix_lblt`, `total_lblt`, `cpfn`, `total_cptl`, `sale_account`, `sale_cost`, `sale_totl_prfi`, `bsop_prti`, `op_prfi`, `thtr_ntin`

---

### `insert_ratios(ratios: List[Dict[str, Any]]) -> int`
- **위치**: Line 81
- **테이블**: `financial_ratios`
- **전략**: ON CONFLICT 없이 항상 신규 INSERT → retrieved_at 별 버전 누적 (PIT 원칙)
- **컬럼**: `stk_cd`, `stac_yymm`, `div_cls_code`, `grs`, `bsop_prfi_inrt`, `ntin_inrt`, `roe_val`, `eps`, `sps`, `bps`, `rsrv_rate`, `lblt_rate`, `cptl_ntin_rate`, `self_cptl_ntin_inrt`, `sale_ntin_rate`, `sale_totl_rate`, `eva`, `ebitda`, `ev_ebitda`, `bram_depn`, `crnt_rate`, `quck_rate`, `equt_inrt`, `totl_aset_inrt`

---

### `get_statements_as_of(stk_cd: str, div_cls_code: str, as_of_date: datetime) -> List[Dict[str, Any]]`
- **위치**: Line 111
- **원리**: `DISTINCT ON (stac_yymm)` + `ORDER BY stac_yymm DESC, retrieved_at DESC`
- **PIT 조건**: `retrieved_at <= as_of_date` (단, `as_of_date < HISTORICAL_CUTOFF`이면 필터 없음)
- **timezone 보정**: `as_of_date.tzinfo is None` → KST 부여
- **반환**: `List[Dict[str, Any]]` (stac_yymm 내림차순)

---

### `get_ratios_as_of(stk_cd: str, div_cls_code: str, as_of_date: datetime) -> List[Dict[str, Any]]`
- **위치**: Line 153
- `get_statements_as_of`와 동일 패턴, `financial_ratios` 테이블 대상

---

## 관련 테이블

| 테이블명 | PK 구성 | 설명 |
|---|---|---|
| `financial_statements` | (stk_cd, stac_yymm, div_cls_code, retrieved_at) | PIT 버전별 재무제표 — 동일 결산기 여러 retrieved_at 공존 가능 |
| `financial_ratios` | (stk_cd, stac_yymm, div_cls_code, retrieved_at) | PIT 버전별 재무비율 |

---

## API 연동

```
GET /api/data/financials?stk_cd=005930&as_of_date=2025-01-01
  → FinancialRepo.get_statements_as_of(stk_cd, div_cls_code, as_of_dt)
  → FinancialRepo.get_ratios_as_of(stk_cd, div_cls_code, as_of_dt)
  → {"statements": [...], "ratios": [...]}
```
