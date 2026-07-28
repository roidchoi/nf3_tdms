# [ERR-007] Container Log Volume Loss and Host Directory Permission Denied

## 1. 개요 및 증상 (Symptoms)
- **발생 환경**: WSL 2 / Docker Compose 가동 환경
- **주요 증상**:
  1. 배치 프로세스(Daily Routine, Financial Collector)가 완료된 후, 대시보드 화면상에 최근 실행 결과가 반영되지 않고 로컬 테스트 결과인 낡은 데이터가 유지되거나, `0/3 CIK`와 같은 더미 메트릭만 표시되는 현상.
  2. 수집 완료 리포트(`.json`)와 실제 텍스트 로그 파일(`.log`)이 호스트 마운트 디렉토리(`./logs/p3_usdms/`, `./logs/p2_kdms/`)에 생성되지 않고 누락되는 현상.
  3. 컨테이너가 재빌드 및 재생성(`docker compose up -d --build`)될 때 과거 대량 수집 실행 결과가 완전히 소멸(휘발)됨.
  4. 호스트에서 `./logs/p3_usdms` 폴더의 소유권 권한 문제(Permission Denied)로 인해 복사 작업이나 파일 접근 시 에러 발생.

---

## 2. 원인 분석 (Root Cause)

### A. 공통 EnvDetector의 환경변수 덮어쓰기 문제
- `p1_shared` 내의 `EnvDetector`는 `.env` 파일을 로딩하면서, 이미 시스템(또는 Docker Compose)에 주입된 환경변수를 강제 덮어쓰기(`os.environ[k] = v`)하는 로직을 가짐.
- `docker-compose.yml`에서 주입한 올바른 로그 저장 경로인 `LOG_DIR=/app/logs`가 무력화되고, `.env`에 정의된 개발 전용 경로인 `LOG_DIR=./logs`로 오버라이드됨.
- 이에 따라 컨테이너 내부 Python 프로세스는 마운트된 볼륨 디렉토리가 아닌 컨테이너 내부의 격리된 임시 경로 `/app/tdms_core/p3_usdms/logs/`에 로그를 적재하게 됨. 결과적으로 호스트 동기화가 풀리고, 컨테이너 재생성 시 모든 이력이 소실됨.

### B. 호스트 디렉토리 소유권 꼬임
- 도커 데몬이 컨테이너 내부에서 로그 디렉토리를 자동 생성할 경우, 호스트의 `./logs/p3_usdms` 및 `./logs/p2_kdms` 디렉토리 소유권이 `root` 계정으로 묶여 일반 호스트 유저 계정에서 쓰기 및 접근 권한 오류 발생.

---

## 3. 해결책 및 조치 내용 (Resolution)

### A. 환경변수 덮어쓰기 우회 - 개별 설정 보정
- 공통 `EnvDetector`를 수정할 경우 다른 모듈의 `.env` 우선순위 의존성이 깨질 위험이 크므로 기존 코드는 100% 원형 복구.
- 대신 `p3_usdms` 및 `p2_kdms`의 개별 `config.py` 생성자(`__init__`) 레벨에서 도커 컨테이너 여부를 감지하여 경로를 보정함.

#### 1) USDMS 보정 코드 (`tdms_core/p3_usdms/config.py`)
```python
    def __init__(self, **values):
        super().__init__(**values)
        if not self.SEC_USER_AGENT:
            raise ValueError("SEC_USER_AGENT 환경변수가 누락되었습니다")

        # 도커 컨테이너 환경일 경우 마운트 폴더 경로를 강제하여 환경변수 덮어쓰기 문제 방지
        import os
        if os.path.exists('/.dockerenv'):
            self.LOG_DIR = "/app/logs"
```

#### 2) KDMS 보정 코드 (`tdms_core/p2_kdms/config.py`)
```python
    def __init__(self, **values):
        super().__init__(**values)
        # 도커 컨테이너 환경일 경우 마운트 폴더 경로를 강제하여 환경변수 덮어쓰기 문제 방지
        import os
        if os.path.exists('/.dockerenv'):
            self.log_dir = "/app/logs"
```

### B. 호스트 디렉토리 소유권 양도
- 호스트 터미널에서 다음 명령을 수행하여 마운트 폴더 소유권을 일반 사용자 계정으로 명시적 양도:
  ```bash
  sudo chown -R roid2:roid2 logs/p2_kdms logs/p3_usdms
  ```

---

## 4. 재발 방지 및 검증 방법
1. 도커 컨테이너 재빌드 후 쉘 접속하여 올바른 마운트 경로가 찍히는지 확인:
   ```bash
   docker compose exec p3_usdms python -c "from p3_usdms.config import get_settings; print(get_settings().LOG_DIR)"
   # 출력 결과: /app/logs
   ```
2. 실행 시 마운트된 호스트 디렉토리 내에 수집 리포트 JSON 파일과 텍스트 로그 파일이 실시간 동기화 생성되는지 모니터링.

---
## 관련 의사 결정 및 참조
- [[p3_usdms_wiki/decisions/dec-009_container_log_directory_force_binding]]
- [[p2_kdms_wiki/decisions/dec-010_container_log_directory_force_binding]]
