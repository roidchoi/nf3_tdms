# Task-008 Walkthrough: DB 백업 실행 및 이력 관리 (개발 PC 백업 허브 모델)

개발 PC 환경에서의 안전한 물리 스냅샷 아카이빙 기능 구현과 서버 PC(운영계) 오제어를 원천 차단하는 강건한 안전장치 설계를 완료하였습니다.

---

## 1. 구현 파일 목록 및 역할

### 백엔드 (Backend)
1. **[MODIFY]** [config.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/config.py)
   * `Settings` 클래스에 물리 데이터 경로(`data_path` = `"/app/data"`) 및 백업 보관 폴더 경로(`BACKUP_BASE_DIR` = `"/app/backups"`) 설정을 추가하였습니다.
2. **[NEW]** [backup_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/backup_service.py)
   * `EnvDetector`를 임포트하여 구동 장비가 `dev` 인지 `server` 인지 판별합니다.
   * `create_backup(tag)`: 개발 환경일 경우 `tar -czf`를 사용하여 `kdms_db`, `usdms_db` 물리 볼륨을 압축하여 아카이빙 스냅샷을 생성합니다. 서버 PC 환경일 경우 `PermissionError`를 던져 원천 차단합니다.
   * `list_backups()`: 아카이브 폴더에 저장된 모든 `*.tar.gz` 백업 파일 목록을 수집하여 용량 및 식별 태그, 생성일시, 무결성 검증 필드(`verified`)를 역순 정렬해 반환합니다.
3. **[MODIFY]** [manager.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/routers/manager.py)
   * 백업 조작을 위한 라우트 3종(`GET /env`, `POST /backup`, `GET /backup/list`)을 신설 결합하였습니다.
   * `POST /backup`은 서버 환경에서 즉각 `403 Forbidden` 예외를 반환하여 의도치 않은 I/O 과부하 및 교란을 API 수준에서 차단합니다.

### 프론트엔드 (Frontend)
1. **[NEW]** [backupStore.ts](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/stores/backupStore.ts)
   * 환경 정보 감지, 스냅샷 생성 트리거 및 이력 조회를 담당하는 Pinia 상태 관리 스토어를 구축하였습니다.
2. **[NEW]** [BackupView.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/views/BackupView.vue)
   * 개발 PC에서 접속한 경우 물리 백업 실행(식별 태그 입력) 및 목록 갱신을 수용하는 UI를 출력합니다.
   * 서버 PC에서 접속한 경우, 스냅샷 생성 컨트롤 전체를 강제 비활성화(`:disabled`)하고 상단에 빨간색 경고 배너를 실시간 표출하여 환경 오인을 방지합니다.
3. **[MODIFY]** [DashboardView.vue](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend/src/views/DashboardView.vue)
   * 글로벌 헤더 로고 우측에 실시간 접속 환경 식별 배지(개발: 🟢녹색 배지, 서버: 🔴적색 점멸 배지)를 추가 탑재하였습니다.
   * 탭 내비게이션에 `💾 백업 및 복구` 탭 버튼 및 `BackupView` 컴포넌트 렌더링 래퍼를 연동하였습니다.

---

## 2. 테스트 검증 결과

### 백엔드 테스트 (Pytest)
* **Tier 2 격리 통합 테스트** (4개 통과):
  * `test_get_env_returns_correct_profile_for_dev`: 환경 조회 API 정상 응답 검증.
  * `test_post_backup_on_server_raises_403_forbidden`: 서버 PC 감지 시 API에서 403 Forbidden 및 차단 사유 리턴 검증.
  * `test_post_backup_on_dev_success`: 개발 환경 내 tar 압축 성공 시나리오 모의 검증.
  * `test_get_backup_list_success`: 백업 이력 목록 파싱 및 변환 검증.
* **Tier 3 실물 통합 테스트** (1개 통과):
  * `test_real_physical_backup_generation_on_dev`: 경량 임시 디렉토리를 구축하여 실제 `tar -czf` 실행 및 압축 아카이브가 정상 용량으로 빌드되고, 이력 조회에 연동되는지 실 기동 검증 완료.

### 프론트엔드 테스트 (Vitest)
* **컴포넌트 단위 테스트** (2개 통과):
  * `BackupView.spec.ts` 내 서버 감지 시 경고 배너 및 버튼/인풋 강제 비활성화 단언 성공.
  * 개발 환경 감지 시 컨트롤 활성화 및 백업 이력 테이블 렌더링 일치 단언 성공.

---

## 3. 다음 단계 개발(T-009)을 위한 제언

* **T-009 안전 복구 개발 방향**:
  * T-009 에서는 생성된 `tar.gz` 백업본을 다시 로컬 DB 디렉토리에 풀어서 덮어씌우는 물리 복구 파이프라인을 구축합니다.
  * 이 과정에서 DB 쓰기 중단을 보장하기 위해 타 백엔드 및 DB 컨테이너를 중지하고 재개하는 **Maintenance Mode 오케스트레이션**이 핵심 과제입니다.
  * 프론트엔드에서 복구 버튼 클릭 시 실수로 인한 복구 방지를 위해 사용자가 직접 `RESTORE LOCAL DB`라는 이중 검펌 문구를 입력해야만 작동하도록 안전장치를 연결해 주어야 합니다.
