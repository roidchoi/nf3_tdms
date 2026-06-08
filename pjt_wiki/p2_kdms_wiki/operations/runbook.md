# p2_kdms 운영 런북 (runbook.md)

> **Sub Project**: p2_kdms
> **마지막 업데이트**: 2026-05-26
> **관련**: `[[p2_kdms_wiki/interfaces/schema_kdms_db.md]]`, `[[p2_kdms_wiki/interfaces/fastapi_lifespan.md]]`, `[[p2_kdms_wiki/environment.md]]`

---

## 사전 조건 (모든 명령 공통)

```bash
# 환경 활성화 (필수)
conda activate tdms_p2_env

# 작업 디렉터리
cd /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms

# 컨테이너 기동 확인
docker ps | grep kdms_timescaledb
```

---

## 1. API 서버 기동 / 종료

### 서버 기동 (개발 — Hot Reload)

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 서버 기동 (운영 — 백그라운드)

```bash
# nohup으로 백그라운드 기동
conda run -n tdms_p2_env nohup uvicorn main:app --host 0.0.0.0 --port 8000 > logs/kdms_api.log 2>&1 &
echo $! > kdms_api.pid
```

### 서버 종료

```bash
kill $(cat kdms_api.pid)
# 또는
pkill -f "uvicorn main:app"
```

### 기동 상태 확인

```bash
curl http://localhost:8000/
# → {"message": "KDMS API is running"}
```

---

## 2. 배치 태스크 — 수동 트리거 (Admin API)

> 서버가 기동 중일 때만 사용 가능. 서버가 없으면 아래 **직접 실행** 섹션 사용.

### 전체 태스크 상태 조회

```bash
curl http://localhost:8000/api/v1/admin/tasks/status | python3 -m json.tool
```

### `daily_update` — 일일 OHLCV + 시총 + 팩터 + 분봉 수집

```bash
# 운영 모드 실행
curl -X POST "http://localhost:8000/api/v1/admin/tasks/daily_update/run" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'

# 테스트 모드 실행 (DB 흐름 검증용, API 미호출)
curl -X POST "http://localhost:8000/api/v1/admin/tasks/daily_update/run" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": true}'
```

**자동 실행 스케줄:** 평일(mon-fri) 17:00 KST (APScheduler cron)

### `financial_update` — PIT 재무제표 수집

```bash
# 운영 모드
curl -X POST "http://localhost:8000/api/v1/admin/tasks/financial_update/run" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'
```

**자동 실행 스케줄:** 매일 19:00 KST (APScheduler cron)

### `backfill_minute_data` — 분봉 갭 탐지 및 백필

```bash
# 기본 기간 (지난 8일 ~ 어제)
curl -X POST "http://localhost:8000/api/v1/admin/tasks/backfill_minute_data/run" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'

# 날짜 범위 지정
curl -X POST "http://localhost:8000/api/v1/admin/tasks/backfill_minute_data/run?start_date=2025-01-01&end_date=2025-01-31" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'
```

**자동 실행 스케줄:** 없음 (수동 트리거 전용)

### `backfill_market_cap` — 시가총액 백필

```bash
# 기본 기간 (최근 30일)
curl -X POST "http://localhost:8000/api/v1/admin/tasks/backfill_market_cap/run" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'

# 날짜 범위 지정
curl -X POST "http://localhost:8000/api/v1/admin/tasks/backfill_market_cap/run?start_date=2025-01-01&end_date=2025-03-31" \
  -H "Content-Type: application/json" \
  -d '{"test_mode": false}'
```

---

## 3. 배치 태스크 — 직접 실행 (서버 없이)

> 서버 미기동 상태에서도 실행 가능. 주로 일회성 작업이나 디버깅 목적.

### `daily_update` 직접 실행

```python
# Python 스크립트에서 직접 호출
import sys
sys.path.insert(0, 'tdms_core/p2_kdms')

from tasks.daily_task import run_daily_update

job_statuses = {}
run_daily_update(job_statuses, test_mode=False)  # test_mode=True 로 드라이런 가능
print(job_statuses)
```

```bash
# 또는 conda 환경에서 Python -c 사용
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -c "
from tasks.daily_task import run_daily_update
job_statuses = {}
run_daily_update(job_statuses, test_mode=True)
print(job_statuses)
"
```

### `financial_update` 직접 실행

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -c "
from tasks.financial_task import run_financial_update
job_statuses = {}
run_financial_update(job_statuses, test_mode=True)
print(job_statuses.get('financial_update', {}).get('last_log'))
"
```

### `backfill_minute_data` 직접 실행

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -c "
from datetime import date
from tasks.backfill_task import run_backfill_minute_data
job_statuses = {}
run_backfill_minute_data(
    job_statuses,
    test_mode=False,
    start_date=date(2025, 1, 1),
    end_date=date(2025, 1, 31)
)
print(job_statuses.get('backfill_minute_data', {}))
"
```

### `run_monthly_backfill.py` — 월 단위 분봉 백필 (장기 작업)

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -m ops.run_monthly_backfill \
  --start 2024-01-01 \
  --end 2024-12-31
```

> ⚠️ 월을 분할하여 순차 실행. 완전히 완료되기까지 수 시간이 걸릴 수 있음.

---

## 4. ops 스크립트 직접 실행

### DB 헬스체크

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -m ops.check_db
```

### 시가총액 backfill (ops/backfill_pipeline.py)

```bash
# 코퍼레이트 액션 의심 종목 탐지 + 팩터/일봉 백필
conda run -n tdms_p2_env python -m ops.backfill_pipeline
```

### p2 마이그레이션 전 백업

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env python -m ops.pre_migration_backup
# tag='pre_p2_migration' 으로 backups/kdms/ 에 저장
```

### DB 불필요 데이터 정리

```bash
conda run -n tdms_p2_env python -m ops.cleanup_database
```

---

## 5. 테스트 실행

```bash
cd tdms_core/p2_kdms
conda run -n tdms_p2_env pytest tests/ -v

# 특정 테스트만 실행
conda run -n tdms_p2_env pytest tests/test_daily_task.py -v
conda run -n tdms_p2_env pytest tests/test_financial_task.py -v
conda run -n tdms_p2_env pytest tests/test_backfill_task.py -v
conda run -n tdms_p2_env pytest tests/test_factor_calculator.py -v

# 커버리지 포함
conda run -n tdms_p2_env pytest tests/ --cov=. --cov-report=term-missing
```

---

## 6. DB 직접 접근

```bash
# 컨테이너 psql 접속
docker exec -it kdms_timescaledb psql -U roid -d kdms_db

# 주요 조회
-- 최근 수집 일봉 확인
SELECT dt, stk_cd, cls_prc FROM daily_ohlcv ORDER BY dt DESC LIMIT 5;

-- 수집 누락 확인
SELECT * FROM daily_ohlcv_gap ORDER BY updated_at DESC LIMIT 20;

-- 수정계수 이력 확인
SELECT stk_cd, event_dt, price_ratio, price_source FROM price_adjustment_factors ORDER BY effective_dt DESC LIMIT 10;

-- 재무제표 PIT 버전 확인
SELECT stk_cd, stac_yymm, retrieved_at FROM financial_statements WHERE stk_cd='005930' ORDER BY stac_yymm DESC, retrieved_at DESC LIMIT 10;

-- 시가총액 최근 수집일 확인
SELECT MAX(dt) as last_dt, COUNT(DISTINCT dt) as total_days FROM daily_market_cap;

-- 분봉 수집 대상 현황 (현재 분기)
SELECT quarter, market, COUNT(*) as cnt FROM minute_target_history GROUP BY quarter, market ORDER BY quarter DESC;
```

---

## 7. 태스크 파이프라인 실행 순서 참조

### `daily_update` 내부 순서

```
0. 휴장일 검사 (trading_calendar 기준)
1. KIS 마스터 ZIP 다운로드 → stock_info UPSERT
2. 활성 종목 리스트 조회 (stock_info WHERE status='listed')
3. [Loop 1] 종목별 순회:
   a. KIS API → daily_ohlcv UPSERT
   b. 시가총액 레코드 빌드 (close * listed_shares)
   c. KIS 45일 Range(raw+adj) → FactorCalculator → price_adjustment_factors UPSERT
   d. Loop 1 사후 팩터 소멸 보정 (10일 이내 이벤트 비교)
4. daily_market_cap 일괄 UPSERT
5. [Loop 2] KIS API 오류 의심 종목 팩터 정밀 검증 및 삭제
6. daily_ohlcv_adjusted 갱신 (최근 30일 배치, SQL CTE 누적곱)
7. 당일 분봉 수집 (minute_target_history → Kiwoom API → minute_ohlcv UPSERT)
```

### `financial_update` 내부 순서

```
1. 활성 종목 전체 조회 (stock_info)
2. [Loop] 종목별 순회:
   a. KIS API 7종 재무 데이터 통합 조회
   b. 결산년월(stac_yymm) 기준 재무제표/비율 병합
   c. _compare_financial_data() 변경 감지
   d. 변경 또는 신규 → INSERT 대기열에 추가
3. financial_statements 벌크 INSERT (ON CONFLICT 없음, PIT 원칙)
4. financial_ratios 벌크 INSERT
```

### `backfill_minute_data` 내부 순서

```
0. minute_target_history에서 현재 분기 대상 종목 조회
   (없으면 TargetSelector 동적 선정 후 저장)
1. daily_ohlcv → trading_calendar 과거 거래일 동기화
2. trading_calendar vs minute_ohlcv 비교 → 완전/일부(< 360건) 누락일 탐지
3. 종목별 '가장 이른 공백일' 기준 작업 목록 생성
4. Kiwoom API 호출 (max_requests=30) → 공백일 데이터만 필터링
5. minute_ohlcv UPSERT
```

---

## 8. 장애 대응 (Quick Troubleshoot)

| 증상 | 점검 순서 |
|---|---|
| API 서버 기동 실패 (`RuntimeError: DB 기동 검증 실패`) | `docker ps`로 컨테이너 확인 → `\d` 로 테이블 존재 여부 확인 → `ops/check_db.py` 실행 |
| EnvDetector "unknown" 감지 | `.env` 내 `TDMS_ENV`, `DEV_HOSTNAME` 변수 존재 여부 확인 |
| `daily_update` 전체 실패 | `job_statuses` 조회 또는 로그에서 `CRITICAL` 레벨 오류 확인 |
| 분봉 수집 대상 없음 (`백필 대상 종목이 없습니다`) | `minute_target_history` 테이블에 현재 분기(e.g. `2025Q2`) 데이터 존재 여부 확인 |
| 재무 수집 결과 없음 (`신규/변경된 재무가 없어 스킵`) | 정상 동작 (변경 사항 없음). 강제 재수집이 필요하면 최신 retrieved_at 행 수동 삭제 후 재실행 |
| `backfill_market_cap` 실패 | `.env` 내 `PUB_DATA_API_KEY` 존재 여부 확인, KRX 공공데이터 API 접근 가능 여부 확인 |
| TimescaleDB 청크 오류 | `docker restart kdms_timescaledb` 후 서버 재기동 |

---

## 9. 크론 스케줄 요약

| 태스크 | 트리거 | 비고 |
|---|---|---|
| `daily_update` | 평일(mon-fri) 17:00 KST | APScheduler cron (서버 내부) |
| `financial_update` | 매일 19:00 KST | APScheduler cron (서버 내부) |
| `backfill_minute_data` | 수동 전용 | Admin API 트리거 또는 직접 실행 |
| `backfill_market_cap` | 수동 전용 | Admin API 트리거 또는 직접 실행 |
