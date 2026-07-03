# [P4-ERR-009] 컨테이너 기반 물리 동기화 시 경로 불일치 및 docker-compose 부재 장애

- **분류**: P4 Manager 에러
- **Severity**: High
- **발생 Task ID**: T-110 (물리 동기화 및 감사 리포팅)
- **Context Link**: [db_sync.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/ops/db_sync.py), [sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/sync_service.py)

## 1. 현상
1. **압축해제 대상 경로 오류**: 로컬 -> 서버 물리 동기화(Push) 시, 3단계인 "서버에 압축을 해제합니다" 단계에서 `tar: Cannot open: No such file or directory` 에러를 뿜으며 해제에 실패했습니다.
2. **컨테이너 정지/기동 오류**: 동기화 파이프라인 전후의 로컬 및 원격지 DB 컨테이너 중지/기동 시 `docker-compose` 명령을 찾을 수 없다는 오류와 함께 프로세스가 강제 중단되었습니다.

## 2. 원인
1. **볼륨 마운트 경로와 호스트 경로의 불일치**: 
   - `p4_backend` 컨테이너 내부에서 구동되는 Python 코드는 로컬 볼륨 경로를 `/app/data`로 인식하여 `data_path` 변수에 담았습니다.
   - 하지만 이 경로를 원격지 SSH 명령어로 그대로 넘겨 `sudo tar -xzf ... -C /app/data/kdms_db`를 수행하도록 명령했고, 원격 서버 호스트 OS 상에는 `/app/data` 디렉토리가 존재하지 않아(실제 경로는 `/home/roid2/pjt/nf3/01_nf3_tdms/data`) 경로 탐색 실패 에러가 유발되었습니다.
2. **컨테이너 내부 `docker-compose` 부재**:
   - `db_sync.py`는 기존에 `docker-compose down` 및 `docker-compose up` 명령어를 활용해 DB 컨테이너를 제어하도록 작성되었습니다.
   - 하지만 백엔드 컨테이너 내부 및 원격 서버 런타임에는 docker-compose 바이너리가 미설치되어 있거나 CLI 연동 플러그인이 미비하여 해당 셸 명령을 실행할 수 없었습니다.

## 3. 해결책
1. **원격지 호스트 경로 동적 보정**:
   - `db_sync.py` 내의 `transfer_data` 및 `fix_permissions` 메서드에서, `data_path`가 컨테이너 경로인 `/app/data`로 시작하는 경우 이를 원격지 호스트의 실제 홈 디렉토리 경로인 `/home/{ssh_user}/pjt/nf3/01_nf3_tdms/data` 형태로 동적으로 파싱/치환하여 전달하도록 보정 로직을 추가했습니다.
   - `data_path` 변경에 대응하여 임시 tar 아카이브 해제 및 소유권 수정(`chown`) 명령어에도 동적으로 변환된 원격 경로가 전달되도록 일원화했습니다.
2. **컨테이너 단독 제어 명령어로 우회**:
   - 디렉토리 진입 및 docker-compose 전체 제어 방식 대신, `/var/run/docker.sock` 마운트 소켓을 활용해 **`docker stop {container_name}`** 및 **`docker start {container_name}`**을 직접 호출하여 대상 DB 컨테이너(`kdms_timescaledb`, `usdms_timescaledb`)만 핀포인트로 내리고 올릴 수 있도록 코드를 고도화했습니다.

## 4. 검증 결과
- 수정 후 물리 동기화 Push 파이프라인 수행 시, `/app/data` 컨테이너 경로가 원격 서버 측 실제 경로(`/home/roid2/pjt/nf3/01_nf3_tdms/data/...`)로 완벽히 자동 치환되어 압축 해제 및 `chown 1000:1000` 권한 교정까지 장애 없이 정상 완수되었습니다.
- docker-compose 대신 direct docker stop/start 명령을 수행함으로써 가상 환경 의존성 없이 로컬/원격 컨테이너 유지보수 모드 제어에 성공했습니다.
