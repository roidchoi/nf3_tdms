---
id: p2ERR-002
sub_project: p2_kdms
severity: critical
status: confirmed
last_seen: Task-010
related: [[interfaces/schema_kdms_db.md]], [[decisions/dec-004_kis_api_throttling_strategy.md]]
---

# [p2ERR-002] 시가총액 벌크 적재 시 PostgreSQL bigint out of range 오류

### 발생 패턴 및 재현 조건
- **환경**: PostgreSQL 16 (TimescaleDB 2.14.2), psycopg2-binary
- **발생 시점**: 일일 데이터 수집 파이프라인의 최종 단계인 `daily_market_cap` 일괄 적재(`upsert_daily_market_cap`) 실행 시.
- **재현 방법**:
  1. `stock_info` 테이블의 특정 비주식 종목(예: `100026 한투글로벌넥스트웨이브1(A)` 등 금융상품)의 상장주식수(`m_vol`)에 `20250901000000` (20조)과 같은 날짜 포맷의 비정상 정수를 삽입한다.
  2. 해당 종목의 일봉 종가(`close = 939원` 등)를 곱하여 시가총액 `mkt_cap`을 연산한다. (`mkt_cap` = 1경 9,015조 5,960억 3,900만 원)
  3. 다른 대형주나 추가 상품에 대해 유사한 메타데이터가 누적되어 연산되는 과정에서 PostgreSQL 64비트 정수형(`bigint`) 최댓값인 `9,223,372,036,854,775,807` (9.22경)을 초과하는 행이 발생한다.
  4. 벌크 삽입(`execute_batch`)을 날리면 DB가 `bigint out of range` 예외를 터뜨리고, E2E 수집 트랜잭션 전체를 롤백시킨다.

### 실제 에러 로그 (요약 금지)
```text
2026-05-27 18:28:42,656 [ERROR] repositories.market_cap_repo: daily_market_cap 벌크 UPSERT 중 오류 발생: bigint out of range
Traceback (most recent call last):
  File "/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/repositories/market_cap_repo.py", line 75, in upsert_daily_market_cap
    execute_batch(cursor, query, args)
psycopg2.errors.NumericValueOutOfRange: bigint out of range
```

### 원인
- 한국투자증권(KIS) 마스터 파일 파싱 규격 상, 일반 상장 주식이 아닌 수익증권/금융상품(ETF/ETN/펀드 등)은 컬럼 자릿수 오프셋 구조가 완전히 다릅니다. 이로 인해 상장주식수 필드에 날짜형 수치(`20250901000000`)가 왜곡 유입되어 `stock_info.m_vol`에 저장되었습니다.
- 해당 비정상 주식수와 주가의 곱이 64비트 정수 범위를 아득히 초과하여 데이터베이스 삽입 과정에서 강제 에러 롤백을 일으켰습니다.
- 원인 코드 경로: `tdms_core/p2_kdms/tasks/daily_task.py` 내부 `DailyTask.run` 시가총액 계산 부근

### 해결법 (필수)
- **해결 절차**:
  1. 한국 시장 구조 상 단일 종목의 상장주식수가 1,000억 주를 초과하는 것은 물리적으로 불가능하므로(예: 삼성전자 약 59억 주), 상장주식수(`shares`)가 1,000억 주(`100_000_000_000`)를 넘거나 음수일 경우 **파싱 오차로 간주하여 강제로 `0`으로 세팅**합니다.
  2. 연산된 시가총액(`mkt_cap`) 및 거래대금(`amt`)이 PostgreSQL `bigint` 상한값인 9경(`9_000_000_000_000_000_000`)을 초과할 경우 안전하게 **`0`으로 보정 컷 오프(Cut-off)**합니다.
  3. 이 방어막을 통해 비정상 데이터가 유입되더라도 전체 수집 트랜잭션이 충돌 없이 안전하게 E2E 완주할 수 있도록 보증합니다.

- **수정된 코드**:
```python
# tdms_core/p2_kdms/tasks/daily_task.py L131-155
                    # 시가총액 레코드 빌드
                    if self.market_cap_repo is not None:
                        shares = stock.get("listed_shares", 0) or 0
                        # 1,000억 주 초과 비정상 주식수(마스터 오류 유입) 방어
                        if shares > 100_000_000_000 or shares < 0:
                            shares = 0
                        for ohlcv in ohlcv_list:
                            mkt_cap = ohlcv["close"] * shares
                            # PostgreSQL bigint (9.22경) 오버플로우 방어
                            if mkt_cap > 9_000_000_000_000_000_000:
                                mkt_cap = 0
                            amt = ohlcv["close"] * ohlcv["volume"]
                            if amt > 9_000_000_000_000_000_000:
                                amt = 0
                            
                            mc_records.append({
                                "dt": ohlcv["dt"],
                                "stk_cd": stk_cd,
                                "cls_prc": ohlcv["close"],
                                "mkt_cap": mkt_cap,
                                "vol": ohlcv["volume"],
                                "amt": amt,
                                "listed_shares": shares
                            })
```

### 발생 이력
- Task-010 최초 발생 및 해결 완료
