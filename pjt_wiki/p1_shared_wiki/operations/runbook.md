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
