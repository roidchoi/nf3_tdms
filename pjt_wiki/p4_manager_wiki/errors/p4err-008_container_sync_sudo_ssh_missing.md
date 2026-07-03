# [P4-ERR-008] 컨테이너 기반 물리 동기화 구동 시 sudo 및 ssh/scp 부재 장애

- **분류**: P4 Manager 에러
- **Severity**: High
- **발생 Task ID**: T-110 (물리 동기화 및 감사 리포팅)
- **Context Link**: [sync_service.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/services/sync_service.py), [backend.Dockerfile](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/backend.Dockerfile), [docker-compose.yml](file:///home/roid2/pjt/nf3/01_nf3_tdms/docker-compose.yml)

## 1. 현상
- 로컬 개발 PC의 `p4_backend` 컨테이너 내부에서 데이터 물리 동기화(밀어넣기/push)를 기동 시, 아래와 같은 OS 명령어 탐색 실패 및 권한 부족 에러가 발생하며 동기화 파이프라인 가동이 차단되었습니다.
  1. `[Errno 2] No such file or directory: 'sudo'`
  2. `[Errno 2] No such file or directory: 'ssh'` 또는 `[Errno 2] No such file or directory: 'scp'`
  3. 원격 서버(192.168.35.176)의 NOPASSWD 설정 및 SSH 접속 인증(Permission Denied) 실패.

## 2. 원인
1. **`sudo` 명령어의 무조건적인 호출**: `sync_service.py` 내부의 로컬 sudo 권한 검증 단계에서 컨테이너 내부 런타임 환경(이미 `root` 사용자거나 `sudo`가 미설치된 상태)을 고려하지 않고 `sudo -n true` 명령을 무조건적으로 셸에 수행하여 발생했습니다.
2. **`ssh`/`scp` 클라이언트 유틸리티 미설치**: `p4_backend` 컨테이너 이미지를 빌드할 때 웹 애플리케이션에 필요한 패키지만 설치하고, 원격 데이터 전송을 위한 SSH/SCP 클라이언트 바이너리(`openssh-client`)를 누락하여 발생했습니다.
3. **SSH 키 바인딩 부재**: 컨테이너 내부에는 호스트 OS에 저장된 SSH 인증 개인키(`~/.ssh/tdms_sync_rsa`)가 복사되거나 마운트되지 않아 비밀번호 없는 SSH 통신이 원천 차단되었습니다. 아울러 원격지의 `/etc/sudoers.d/tdms_sync` NOPASSWD 리스트에는 제한된 명령어(`tar`, `rm`, `chown`, `docker`)만 허용되어 있어 `sudo -n true` 검증 자체가 거절되었습니다.

## 3. 해결책
1. **로컬 `sudo` 조건부 검증 보완**:
   - `sync_service.py` 내의 `sudo` 자격 검증 전에 `shutil.which("sudo")`를 통해 `sudo` 유틸리티 존재 여부를 먼저 감지하도록 수정하였습니다.
   - 아울러, 무인 패스워드 검증을 위해 `sudo -n true` 대신 NOPASSWD 허용 목록에 있는 **`sudo -n docker --version`**을 호출하여 비밀번호 없이 sudo 사용이 가능한지 합리적으로 검증하도록 수정했습니다.
2. **`openssh-client` 설치**:
   - `tdms_core/p4_manager/backend.Dockerfile`의 APT 설치 의존성에 `openssh-client` 패키지를 추가하여 이미지를 다시 빌드하도록 변경했습니다.
3. **SSH 키 및 Docker 소켓 바인딩 추가**:
   - `docker-compose.yml` 파일의 `p4_backend` 볼륨 바인딩 옵션에 **`- ~/.ssh:/root/.ssh:ro`**를 추가하여 호스트의 SSH 디렉토리를 컨테이너 내부에 읽기 전용으로 안전하게 공유하도록 조치했습니다.

## 4. 검증 결과
- 컨테이너 이미지 재빌드 및 재시작 후 `sudo`, `ssh`, `scp` 관련 파일 못 찾음(No such file or directory) 장애가 완전히 해소되었습니다.
- 호스트의 인증 키가 연동됨에 따라 원격지 서버와의 SSH 터널이 패스워드 입력 요구 없이 성공적으로 뚫리고 1단계 점검(Preflight Check)을 통과함을 확인했습니다.
