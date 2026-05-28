# Interface: FastAPI App & Lifespan (main.py)

> **파일**: `tdms_core/p2_kdms/main.py`
> **역할**: FastAPI 앱 진입점 — DB 풀 초기화, 검증, APScheduler 크론 등록
> **관련**: `[[interfaces/data_api_endpoints.md]]`, `[[interfaces/settings_config.md]]`, `[[codebase_map.md]]`

---

## 앱 상수

```python
CONTAINER_NAME = "kdms_timescaledb"
VOLUME_NAME    = "kdms_pgdata"
BACKUP_DIR     = "backups/kdms"

KDMS_EXPECTED_TABLES = [
    "daily_ohlcv", "stock_info", "price_adjustment_factors",
    "financial_statements", "financial_ratios", "daily_market_cap",
    "system_milestones", "minute_target_history",
]
KDMS_MIN_ROW_COUNTS = {"daily_ohlcv": 1_000_000}
```

---

## 전역 job_statuses

```python
job_statuses = {
    "daily_update":        {"is_running": False, "last_status": "none"},
    "financial_update":    {"is_running": False, "last_status": "none"},
    "backfill_minute_data":{"is_running": False, "last_status": "none"},
    "backfill_market_cap": {"is_running": False, "last_status": "none"}
}
```

> `routers/admin.py`와 공유 — 태스크 중복 실행 방지에 사용.

---

## lifespan (기동/종료 순서)

```
기동 시:
  1. create_kdms_pool()          → app.state.pool
  2. BackupManager 초기화
  3. StartupValidator.validate()  → KDMS_EXPECTED_TABLES + KDMS_MIN_ROW_COUNTS
     └─ is_healthy=False → RuntimeError (서비스 기동 차단)
  4. AsyncIOScheduler(timezone="Asia/Seoul") 생성
  5. admin_module.scheduler, job_statuses 주입
  6. 크론 등록:
     - daily_update:     평일(mon-fri) 17:00 KST
     - financial_update: 매일 19:00 KST
     (backfill_minute_data: 수동 트리거만 유지, 크론 제거)
  7. scheduler.start()

종료 시:
  1. scheduler.shutdown()
  2. pool.close_all()
```

---

## 라우터 등록

```python
app.include_router(data_router)                          # prefix: /api/data
app.include_router(admin_router, prefix="/api/v1/admin") # prefix: /api/v1/admin
```

| 경로 | 라우터 |
|---|---|
| `/` | 헬스체크 ({"message": "KDMS API is running"}) |
| `/api/data/*` | `routers/data.py` |
| `/api/v1/admin/*` | `routers/admin.py` |
