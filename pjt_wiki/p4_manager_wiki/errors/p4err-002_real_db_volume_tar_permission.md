# [P4ERR-002] 대용량 Docker DB 볼륨(66GB) tar 백업 시 I/O 지연 및 권한 미획득 (Permission Denied)

---

## 1. 에러 현황 및 배경
* **발생 원인**: 로컬 개발 및 E2E 테스트 과정에서 `/api/mgr/backup`을 호출하여 TimescaleDB 물리 볼륨 디렉토리 `/app/data`를 아카이빙하려 할 때, 다음 두 가지 병목이 발생하였습니다:
  1. **대용량 문제**: 로컬 개발 TimescaleDB 데이터 폴더 용량이 약 66GB에 달해, 전체를 압축(tar.gz)하는 작업은 수십 분이 소요되며 디스크 용량 소모 및 I/O 락을 초래합니다.
  2. **권한 미획득 (Permission Denied)**: Docker 컨테이너 내부에서 기동된 TimescaleDB가 생성한 파일들은 호스트 기준 `root:root` 권한으로 생성됩니다. 일반 사용자 권한을 지닌 P4 매니저 프로세스나 pytest 테스트 프로세스가 단순 `tar -czf` 명령을 통해 해당 폴더에 직접 접근하여 읽으려 할 경우, `Permission denied` 에러를 던지며 아카이빙이 중단됩니다.

---

## 2. 해결책 및 방어 설계

### 2.1. 런타임 우회 및 통합 테스트 격리 (T-008 해결 패턴)
통합 테스트(Tier 3) 수행 중 66GB 볼륨의 전체 압축 및 권한 오류를 원천 차단하기 위해, 실제 DB 경로를 압축하지 않고 **테스트 전용 임시 데이터 디렉토리를 격리 구축**하는 우회법을 도입했습니다.

1. **테스트 설정 임시 오버라이딩**:
   테스트 코드(`test_backup.py`) 실행 시, `tmp_path` 하위에 더미 `kdms_db/dummy.txt` 및 `usdms_db/dummy.txt` 파일을 갖춘 격리 폴더를 자동 생성합니다.
2. **Settings 주입**:
   `p4_manager.config.settings.data_path`를 해당 `tmp_path` 경로로 일시 우회 전환합니다.
3. **로직 파이프라인 검증**:
   이를 통해 실제 66GB 볼륨 대신 1KB 미만의 더미 파일들로 구성된 임시 경로를 타겟팅하므로, `Permission denied` 없이 0.2초 이내에 실제 `tar -czf` subprocess 실행 로직과 아카이브 생성 여부를 안전하고 신속하게 검증할 수 있습니다.

### 2.2. 운영 상의 해결책
실 런타임 환경에서 물리 백업을 완벽히 실행하기 위해서는 다음 조치가 확보되어야 합니다:
1. Docker Compose 내부에서 백엔드 볼륨 폴더의 읽기 권한을 P4 백엔드 컨테이너와 적절히 마운트 공유해야 합니다.
2. 또는 백업 전용 스크립트가 root 권한을 획득하여 실행되도록 시스템 차원의 sudoers 설정을 연동해야 합니다.

---

## 3. 관련 파일 및 레퍼런스
* **격리 검증 테스트 코드**: [test_backup.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_backup.py#L75-L100) (임시 디렉토리 주입 및 실제 tar 기동 검증)
* **백업 코어 서비스**: [backup_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/backup_service.py)
