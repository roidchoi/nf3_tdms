# Error: TimescaleDB 논리 복원 실패 (하이퍼테이블 메타데이터 충돌)

> **에러 ID**: P1-ERR-002
> **Severity**: High (결국 ADR-001로 아키텍처 변경 유발)
> **발생 Task**: T-008 이전 단계 (2026-05-07 마이그레이션)
> **상태**: 해결됨 (물리 복제로 우회)
> **관련**: `[[decisions/dec-001_physical_sync.md]]`

---

## 에러 메시지

```
pg_restore: error: could not execute query:
  ERROR: relation "daily_ohlcv" does not exist

pg_restore: error: could not execute query:
  ERROR: insert or update on table "daily_ohlcv"
         violates foreign key constraint "daily_ohlcv_stk_cd_fkey"
```

또는 시스템 마비:

```
out of shared memory
```

---

## 원인

1. **TimescaleDB 버전 불일치**: 개발PC 2.14.2, 서버PC 2.15.0 → 카탈로그 호환 불가
2. **FK/인덱스 순서**: `pg_restore -j 8` 병렬 복원 시 FK가 데이터보다 먼저 생성됨
3. **대용량 한계**: 37GB 복원 시 shared_memory 부족으로 PostgreSQL 자체 마비

---

## 해결법

**근본 해결**: 논리 복원 대신 `PhysicalSyncManager`의 물리 Stop-and-Copy 방식 사용 (`[[decisions/dec-001_physical_sync.md]]`)

**소용량 복원 시 (BackupManager 사용 시)**: `section_order=True`로 pre-data → data → post-data 순서 복원 (`[[decisions/dec-002_pg_restore_section_order.md]]`)

---

## 발생 이력

| Task | 날짜 | 환경 | 비고 |
|---|---|---|---|
| T-008 이전 | 2026-05-07 | 개발PC → 서버PC | 약 6시간 시도 후 물리 복제로 전환 |
