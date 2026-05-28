# ADR-001: 논리적 동기화 폐기 → 물리적 Stop-and-Copy 채택

> **결정일**: 2026-05-07 (KDMS 마이그레이션 실패 후)
> **Task**: T-008
> **상태**: 확정 (적용됨)
> **관련**: `[[interfaces/physical_sync_manager.md]]`, `[[interfaces/backup_manager.md]]`

---

## 배경 (Context)

개발PC ↔ 서버PC 간 37GB+, 2.5억 건의 TimescaleDB 데이터를 전송해야 했다.
초기 설계는 `pg_dump -Fc` + `pg_restore` 기반 논리적 동기화였다.

---

## 문제 (Problem)

### 실패 1: 논리적 복원 (pg_dump / pg_restore)
- TimescaleDB 하이퍼테이블 메타데이터(Catalog) 불일치 → 복원 후 테이블 조회 불가
- `out of shared memory` 오류로 시스템 마비
- 에러: `relation "daily_ohlcv" does not exist` (FK 순서 문제)

### 실패 2: 가동 중 복원
- 백엔드 컨테이너가 켜진 상태에서 복원 → 스케줄러가 자동 실행되어 데이터 오염(Pollution)
- 5/7 당일 데이터 유입 확인

### 실패 3: 볼륨 마운트 경로 불일치
- `/var/lib/postgresql/data` 주입 → 엔진은 `/home/postgres/pgdata/data` 참조
- 데이터가 증발한 것처럼 보이는 현상

---

## 결정 (Decision)

**물리적 Stop-and-Copy 방식으로 전환**:
1. 모든 앱/DB 컨테이너 중지 (Maintenance Mode)
2. `tar -czf - . | ssh ... | tar -xzf -` 파이프라인으로 실시간 물리 전송
3. 권한 교정 (`chown 1000:1000`)
4. 컨테이너 재기동

**이유**:
- 디스크에 저장된 실제 데이터 블록 파일 자체를 복제 → 100% 무결성 보장
- 논리 변환 없음 → 하이퍼테이블 메타데이터 충돌 없음
- 컨테이너 중지 → 데이터 오염 원천 차단

---

## 결과 (Outcome)

- 2026-05-07: 37GB KDMS 데이터 14분 전송 완료 (35.2MB/s rsync 기준)
- 18개 테이블 100% 무결성 대조 확인 (`audit_deep.py` 결과)

---

## 트레이드오프

| 장점 | 단점 |
|---|---|
| 100% 무결성 | 전송 중 DB 서비스 중단 필요 |
| 대용량 지원 | sudo 권한 필요 |
| 구현 단순 | 부분 동기화 불가 (전체 DB 단위) |

---

## 폐기된 모듈

- `ops/sync_manager.py` (`SyncManager`, `FullSyncSafetyChecker`) — 코드는 잔존하나 **실운영에서 사용 금지**
- `task-009_spec.md` — T-008에 통합 흡수됨
