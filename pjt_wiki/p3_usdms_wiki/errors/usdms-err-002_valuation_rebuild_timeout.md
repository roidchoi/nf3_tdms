---
id: USDMS-ERR-002
sub_project: p3_usdms
severity: high
status: confirmed
last_seen: Task-005
related: [[p3_usdms_wiki/interfaces/valuation_repo.md]]
---

# [USDMS-ERR-002] Valuation 자가치유 갭 탐색 쿼리 실행 지연 및 타임아웃

### 발생 패턴 및 재현 조건
- **환경**: WSL 2 (Ubuntu 24.04), PostgreSQL 16 (TimescaleDB)
- **발생 시점**: `DailyRoutine.run()` 실행 중 Step 4 `ValuationCalculator.calculate_and_save(cik, rebuild=False)` 기동 시
- **재현 방법**:
  1. 약 10년 치(3000일 이상) 일일 가격(`us_daily_price`)이 적재되어 있는 상태에서 가치평가 데이터가 완전히 없는 종목을 스캔.
  2. `ValuationRepo.get_earliest_valuation_gap_date`를 호출하여 가격 대비 가치지표 공백 최초 날짜 조회.
  3. 전체 테이블 조인 병목으로 인해 쿼리 수행 속도가 40초를 초과하여 타임아웃 경고 발생.

### 실제 에러 로그 (요약 금지)
```text
psycopg2.errors.QueryCanceled: canceling statement due to user request timeout
OR
Slow Query Warning: get_earliest_valuation_gap_date executed in 42.15 seconds.
```

### 원인
- `get_earliest_valuation_gap_date` 쿼리가 과거 10년 치 가격 전체(`us_daily_price`)와 가치평가 테이블(`us_daily_valuation`)을 아우터 조인하여 가치평가 결측(Null)인 날짜 중 가장 빠른 날짜를 조회하려 시도함.
- 조회 범위가 한정되지 않고 인덱스가 범위 밖으로 이탈하여 DB 풀 스캔 유발.
- 원인 코드 경로: `tdms_core/p3_usdms/repositories/valuation_repo.py`

### 해결법 (필수)
- **해결 절차**:
  1. 갭 스캔 윈도우 범위를 최근 60일로 국한하도록 `get_earliest_valuation_gap_date` 쿼리에 `start_date` 파라미터를 추가하고 `p.dt >= %s` 조건을 결합.
  2. ETF 등 재무제표가 아예 없어 갭 탐색 시 무조건 전체 기간 스캔에 걸리는 종목을 필터링하기 위해, 갭 판별 SQL에 재무제표 및 주식수가 실재하는 종목에 대해서만 조인하는 `EXISTS` 하위 조건을 추가.
- **수정된 코드**:
```python
    def get_earliest_valuation_gap_date(self, cik: str, start_date: str = None) -> Optional[date]:
        """
        주식 가격 데이터는 존재하지만 가치평가 데이터가 누락된 가장 이른 날짜를 조회합니다.
        start_date가 지정되면 해당 날짜 이후의 범위 내에서만 갭을 탐색합니다. (대용량 쿼리 최적화)
        """
        cik_padded = str(cik).zfill(10)
        query = """
            SELECT MIN(p.dt) as gap_dt
            FROM us_daily_price p
            LEFT JOIN us_daily_valuation v ON p.cik = v.cik AND p.dt = v.dt
            WHERE p.cik = %s
              AND v.dt IS NULL
        """
        params = [cik_padded]
        if start_date:
            query += " AND p.dt >= %s"
            params.append(start_date)

        with self.get_cursor() as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()
            if row and row['gap_dt']:
                return row['gap_dt']
            return None
```

### 발생 이력
- Task-005 최초 발생 (자가 치유 복구 기동 시, 10년 대량 적재 종목 스캔 정체 감지 후 수정 완료)
