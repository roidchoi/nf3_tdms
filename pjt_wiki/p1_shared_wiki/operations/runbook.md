# 운영 런북 (runbook.md)

> **Sub Project**: p1_shared
> **마지막 업데이트**: 2026-05-14

---

## 1. DB 동기화 (일상 운영)

### 서버 최신 데이터 → 개발PC (Pull)

```bash
# KDMS (한국 주식)
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction pull

# USDMS (미국 주식)
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction pull
```

### 개발PC 데이터 → 서버 (Push)

```bash
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db kdms --direction push
conda run -n tdms_p1_env python -m p1_shared.ops.db_sync --db usdms --direction push
```

> ⚠️ **파괴적 작업**: 대상 PC의 DB를 통째로 덮어씀. 방향 확인 필수.

---

## 2. 동기화 후 무결성 감사

```bash
# 1단계: 빠른 통계 비교 (락 없음, 1초 내 완료)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_fast

# 2단계: 정밀 검증 (행 수 정확 카운트 + PK/Index + 첫/끝 행 대조)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_deep

# USDMS 전용 (10개 테이블 전수 대조)
conda run -n tdms_p1_env python -m p1_shared.ops.auditors.audit_usdms
```

---

## 3. 수동 백업 (DB 스냅샷)

```python
from p1_shared.ops.backup_manager import BackupManager

mgr = BackupManager(
    container_name="kdms_timescaledb",
    db_name="kdms_db",
    db_user="roid",
    backup_dir="./backups/kdms",
    volume_name="kdms_pgdata",
)
dump_path = mgr.backup(tag="manual")
print(f"백업 완료: {dump_path}")
```

---

## 4. Docker 재기동 후 DB 기동 검증

```python
from p1_shared.db.connection import DbConnectionPool
from p1_shared.ops.startup_validator import StartupValidator
from p1_shared.ops.backup_manager import BackupManager

pool = DbConnectionPool(dsn="postgresql://roid:pass@localhost:5432/kdms_db")
backup_mgr = BackupManager("kdms_timescaledb", "kdms_db", "roid", "./backups", "kdms_pgdata")
validator = StartupValidator(pool=pool, backup_manager=backup_mgr)

report = validator.validate(
    db_name="kdms",
    expected_tables=["daily_ohlcv", "stock_info"],
    min_row_counts={"daily_ohlcv": 1_000_000},
)
validator.print_report(report)

if not report.is_healthy:
    print("❌ DB 비정상 — 복구 필요")
pool.close_all()
```

---

## 5. 테스트 실행

```bash
# 단위 테스트 전체 (실 DB 불필요)
conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/ -v --ignore=tests/test_*_integration.py

# 통합 테스트 (실 DB 필요)
conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/ -m integration -v

# 특정 모듈만
conda run -n tdms_p1_env pytest tdms_core/p1_shared/tests/test_connection.py -v
```

---

## 6. sudoers 무인화 설정 (1회만)

```bash
# 개발PC & 서버PC 양쪽에서 각 1회 실행
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/tar, /usr/bin/rm, /usr/bin/chown, /usr/bin/docker" \
  | sudo tee /etc/sudoers.d/tdms_sync
```

---

## 7. 개발 PC vs 서버 PC 1:1 Dual Run 데이터 정합성 검증

개발 PC의 최적화된 데이터 수집기(배포 예정본)와 실서버 PC의 기존 수집기(운영계) 간의 적재 데이터 품질 및 정합성을 비교 분석하기 위한 1:1 교차 검증 도구입니다.

### 실행 방법

프로젝트 루트의 `verify_dual_run.py` 스크립트를 실행합니다. 각 시장(KDMS, USDMS)의 개발용 DB DSN과 실서버 DB DSN을 인자로 전달하여 1:1 품질 대조를 수행합니다.

```bash
# 가상환경 기동 하에서 검증 도구 호출 예시
python verify_dual_run.py \
  --dev-kdms-dsn "postgresql://roid:pass@localhost:5432/kdms_db" \
  --srv-kdms-dsn "postgresql://roid:pass@192.168.35.205:5432/kdms_db" \
  --dev-usdms-dsn "postgresql://roid:pass@localhost:5432/usdms_db" \
  --srv-usdms-dsn "postgresql://roid:pass@192.168.35.205:5432/usdms_db" \
  --start-date "2026-07-01" \
  --end-date "2026-07-14"
```

### 주요 검증 내용
1. **KDMS (한국 주식)**
   - `daily_ohlcv` 테이블의 시작~종료 기간 내 총 적재 행(row) 수 대조.
   - 서버 PC에는 적재되었으나 개발 PC에는 누락된 종목/날짜 목록(Left Join) 검출.
   - 시가, 고가, 저가, 종가 및 거래량이 양측 DB에서 오차 없이 100% 일치하는지 정밀 대조.
2. **USDMS (미국 주식)**
   - `us_daily_valuation` 테이블의 지정 기간 내 총 적재 행 수 대조.
   - 서버 대비 개발 PC의 누락 데이터 검출.
   - 시가총액, PE, PB 등의 가치지표 산출 수치에 부동소수점 오차(1% 미만 허용오차 범위) 내 정합성 검증.
