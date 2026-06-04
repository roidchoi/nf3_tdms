# ADR-002: pg_restore 섹션 분리 전략 (pre-data → data → post-data)

> **결정일**: 2026-05-06 (T-006 BackupManager 구현 중)
> **Task**: T-006
> **상태**: 확정 (적용됨)
> **관련**: `[[p1_shared_wiki/interfaces/backup_manager.md]]`

---

## 배경

`pg_restore -j 8` (병렬 복원) 사용 시 인덱스와 FK가 데이터보다 먼저 생성되어 INSERT 실패 발생.

---

## 문제

```
pg_restore: error: could not execute query:
  ERROR: insert or update on table "daily_ohlcv" violates foreign key constraint
```

병렬 복원(-j 8)에서 worker들이 인덱스/FK와 데이터를 동시에 처리하여 순서가 꼬임.

---

## 결정

`BackupManager.restore()`에서 `section_order=True` 기본값으로 3단계 순차 복원:

```python
# 1단계: 스키마만 (CREATE TABLE, extension 등)
pg_restore --section=pre-data -d {db_name} {dump_path}

# 2단계: 데이터만 (INSERT)
pg_restore --section=data -d {db_name} {dump_path}

# 3단계: 인덱스/FK (CREATE INDEX, ADD CONSTRAINT)
pg_restore --section=post-data -d {db_name} {dump_path}
```

---

## 결과

- FK 충돌 없이 안정적 복원 완료
- 병렬 복원보다 속도는 느리나 실용 범위 내 (소용량 백업 복원 기준)
- 대용량(37GB+)에서는 어차피 ADR-001의 물리 복제 사용

---

## 주의사항

- `section_order=False` (기본 복원)는 소용량 테스트 DB에서만 사용할 것
- TimescaleDB 환경에서는 항상 `section_order=True` 권장
