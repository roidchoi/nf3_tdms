# T-002 EnvDetector 구현 Walkthrough

## 1. 구현 개요
- **대상 Task**: T-002 환경 감지 모듈 (`utils/env_detector.py`)
- **목표**: `TDMS_ENV` 명시, hostname, IP 주소를 기반으로 현재 실행 환경(개발PC/서버PC)을 감지하고, 해당 환경에 맞는 설정값을 반환하는 `EnvDetector` 클래스 구현

## 2. 변경된 파일 목록
- **추가**: `tdms_core/p1_shared/p1_shared/utils/env_detector.py`
  - `get_local_ips()`: `ip addr` 명령어를 파싱하여 루프백 및 WSL 가상 IP를 제외한 내부망 IP 반환
  - `EnvDetector`: 환경 감지 핵심 로직 구현 (`detect`, `load_env_profile`, `get_peer_host` 메서드)
- **추가**: `tdms_core/p1_shared/tests/test_env_detector.py`
  - 15개의 단위 테스트 케이스 작성 (정상, 경계값, 예외, 통합/연계 케이스)

## 3. 주요 구현 내용
1. **환경 감지 우선순위 로직 (`detect()`)**:
   - 1순위: `TDMS_ENV` 환경변수 (명시적 지정)
   - 2순위: Hostname 매칭 (대소문자 무시)
   - 3순위: IP 매칭 (`subprocess.run(["ip", "-4", "addr", "show"])`를 통한 IP 획득 후 비교)
   - 위 조건 불만족 시 `"unknown"` 반환.
2. **동기화 상대방 정보 조회 (`get_peer_host()`)**:
   - 감지된 환경에 따라 `SERVER_IP` 또는 `DEV_IP` 대칭적 반환 로직 구현.
3. **환경 프로파일 반환 (`load_env_profile()`)**:
   - 현재 환경의 ip, hostname과 상대 환경의 ip, hostname을 dict 형태로 패키징하여 리턴.

## 4. 테스트 결과
- `test_env_detector.py` 15개 단위 테스트 통과 (All Green)
- 기존 T-001 20개 테스트 회귀 검증 통과
- **총 35개 테스트 통과** (`pytest tests/ -v` 기준)

## 5. 설계 결정사항 및 주의점
- `python-dotenv`의 `load_dotenv`를 초기화 시점에 사용하여 `.env`의 값을 읽어들이도록 했으며, `TDMS_ENV=""` 형태로 빈 값이 로드되는 경우를 대비해 `tdms_env` 변수의 strip 및 boolean check(`if tdms_env:`) 로직을 추가하여 fallback 처리함.
- `IP` 주소 조회를 외부 라이브러리(`netifaces` 등) 대신 내장 `subprocess`를 이용하여 가볍게 구현함.
- `RuntimeError`의 예외 메시지 대소문자를 `unknown environment`로 소문자로 변경하여 테스트의 정규식 검사와 일치시킴.

## 6. 다음 Task 진행 시 유의사항
- `T-003 DB 커넥션 풀`이나 `T-008 DB 동기화 매니저` 구현 시, 이 모듈을 초기화하고 `load_env_profile()` 또는 `get_peer_host()`를 호출하여 필요한 접속 정보를 얻도록 연동해야 합니다.
