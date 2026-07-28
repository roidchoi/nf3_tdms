# [DEC-012] KDMS 태스크 상태 디스크 JSON 영구 적재 및 재시작 자동 복원

> **최초 작성일**: 2026-07-29  
> **관련 모듈**: [`tdms_core/p2_kdms/routers/admin.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/routers/admin.py), [`tasks/daily_task.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/tasks/daily_task.py), [`config.py`](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p2_kdms/config.py)

---

## 1. 개요 및 의사결정 배경

서버 PC 배포 운영 중 가상머신 또는 서버 PC를 재시작했을 때, 미국 백엔드(USDMS)는 품질 요약 및 이전 실행 이력이 유지되는 반면, 한국 백엔드(KDMS)는 품질 요약 및 실행 이력이 백지 상태로 소멸하고 이전 로그 스트리밍 버퍼가 보이지 않는 현상이 식별되었습니다.

### 원인 분석 (Root Cause)
1. **상태 보관 방식의 차이**: USDMS는 태스크 완료 시 `logs/daily_routine_YYYYMMDD_HHMMSS.json` 파일로 실행 리포트를 디스크에 적재하고 API 호출 시 디스크에서 복원했으나, KDMS는 RAM 메모리 딕셔너리(`job_statuses = {}`)로만 관리하여 재부팅 시 RAM 데이터가 초기화됨.
2. **설정 속성 명칭 불일치**: KDMS `config.py`의 `log_dir` 소문자 선언으로 인해 `.env` 및 환경변수 대문자 `LOG_DIR`와의 바인딩 꼬임이 발생하여 로그 파일 마운트 연동에 차질이 있었음.

---

## 2. 해결 및 구현 내용 (Resolution)

### A. 디스크 리포트 JSON 영구 적재 (`save_task_report_json`)
* KDMS 배치 태스크(`daily_update`, `financial_update`, `backfill_market_cap` 등)가 완료되거나 실패할 때, 수집 메트릭과 단계별 소요시간(steps) 데이터를 **`logs/{task_id}_YYYYMMDD_HHMMSS.json` 파일로 디스크에 영구 적재**하도록 구현.

### B. 재시작 시 자동 상태 복원 (`restore_task_statuses_from_disk`)
* `/api/v1/admin/tasks/status` 조회 시, 디스크 `logs/` 디렉터리에 남아있는 최근 `.json` 리포트 파일 10개를 최신순으로 스캔하여 `job_statuses` 메모리를 디스크로부터 자동 복원(Restore)하도록 구현.

### C. 설정 속성 호환성 보장 (`config.py`)
* `config.py` 내에 `LOG_DIR`와 `log_dir` 속성을 모두 정의하고 도커 환경(`/.dockerenv`) 여부에 따라 `/app/logs`로 바인딩 경로를 강제 일치시킴.

---

## 3. 결과 및 검증 (Verification)

* 서버 PC 재부팅 및 `p2_kdms` 컨테이너 재시작 후에도 이전 품질 요약 메트릭, 실행 이력 시간, 최근 100줄 로그 버퍼 스트리밍이 100% 정상 출력됨을 보장함.
* Pytest 유닛 테스트 26개 100% 통과 확인.
