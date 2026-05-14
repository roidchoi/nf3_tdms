# 프로젝트 개요 (overview.md)

> **프로젝트**: NF3 TDMS (Total Data Management System)
> **마지막 업데이트**: 2026-05-14 (p1_shared 완료)
> **역할**: 전체 Sub Project 현황 및 아키텍처 요약

---

## 1. 전체 진행도

| Sub Project | 목적 | 상태 | 진행도 |
|---|---|---|---|
| **p1_shared** | 공통 인프라 라이브러리 (API 클라이언트, DB 풀, 백업, 동기화) | ✅완성 | 100% (T-001~T-008) |
| **p2_kdms** | 한국 주식 데이터 수집·저장 백엔드 | ⬜미착수 | 0% |
| **p3_usdms** | 미국 주식 데이터 수집·저장 백엔드 | ⬜미착수 | 0% |
| **p4_manager** | 통합 관리 레이어 | ⬜미착수 | 0% |

**전체**: Task 8/N 완료 (p1_shared Phase 완료)

---

## 2. 현재 활성 작업

- **완료 Sub Project**: p1_shared
- **완료 Task**: T-001~T-008 전체
- **다음 예정**: p2_kdms 또는 p3_usdms 구현 시작

---

## 3. 시스템 전체 데이터 흐름

```
[KIS API / Kiwoom API]
      │ KisApiCore / KiwoomApiCore (p1_shared)
      ▼
[p2_kdms 수집] ──→ [kdms_db (TimescaleDB, port 5432)]
[p3_usdms 수집] ──→ [usdms_db (TimescaleDB, port 5435)]
      │
      ▼ BackupManager / PhysicalSyncManager (p1_shared)
[개발PC ↔ 서버PC 동기화]
      │
      ▼ audit_fast / audit_deep / audit_usdms (p1_shared)
[무결성 감사]
```

---

## 4. 주요 이정표

| 날짜 | 내용 |
|---|---|
| 2026-04-28 | NF3 TDMS 프로젝트 시작, PRD 작성 |
| 2026-04-30 | p1_shared PRD 확정, Task 계획 수립 |
| 2026-05-06 | T-001~T-007 구현 완료 |
| 2026-05-07 | KDMS 37GB 마이그레이션 (논리→물리 복제 전환) |
| 2026-05-12 | T-008 PhysicalSyncManager 구현 완료, T-009 폐기 |
| 2026-05-14 | p1_wiki 지식화 완료 |