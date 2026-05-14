# Error: TimescaleDB 볼륨 Permission Denied (UID Mismatch)

> **에러 ID**: P1-ERR-001
> **Severity**: High
> **발생 Task**: T-008 (KDMS 마이그레이션 2026-05-07)
> **상태**: 해결됨
> **관련**: `[[decisions/dec-001_physical_sync.md]]`, `[[interfaces/physical_sync_manager.md]]`

---

## 에러 메시지

```
postgres: could not access the server configuration file
  "/var/lib/postgresql/data/postgresql.conf": Permission denied
```

또는:

```
initdb: error: could not access directory "/var/lib/postgresql/data": Permission denied
Waiting for permissions on /var/lib/postgresql/data (999:999 -> 1000:1000)
```

---

## 원인

물리 복제 후 수신 측 폴더의 소유자 UID가 전송 측과 불일치.
- 전송 측: UID 1000 (호스트 사용자)
- 수신 측 컨테이너 기대값: UID 1000 또는 999 (환경마다 다름)
- `tar` 압축 해제 시 원본 UID 메타데이터가 그대로 전달됨

---

## 해결법

```bash
# 수신 측에서 실행 — 1000:1000으로 강제 교정
docker run --rm -v {volume_name}:/data alpine chown -R 1000:1000 /data
```

또는 `PhysicalSyncManager.fix_permissions()` 자동 호출 (T-008 파이프라인 4단계).

---

## 발생 이력

| Task | 날짜 | 환경 | 비고 |
|---|---|---|---|
| T-008 | 2026-05-07 | 서버PC | 999:999 → 1000:1000으로 2차 교정 필요했음 |
