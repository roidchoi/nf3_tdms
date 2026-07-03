# [P4-ERR-011] 도커 컴포즈 빌드 기본값 설정에 의한 서버 PC 환경 오인식

- **분류**: P4 Manager 에러
- **Severity**: Medium
- **Context Link**: [docker-compose.yml](file:///home/roid2/pjt/nf3/01_nf3_tdms/docker-compose.yml), [env_detector.py](file:///home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p1_shared/p1_shared/utils/env_detector.py)

## 1. 현상
- 배포된 서버 PC(192.168.35.176)의 매니저 웹 UI에 접속했으나, 상단 접속 환경 배지가 "서버 PC (운영계)" 대신 "개발 PC 환경"으로 오표시되는 결함이 발견되었습니다.

## 2. 원인
1. **컨테이너 환경 내 자동 감지 제한**:
   - `EnvDetector`는 호스트 OS에서 직접 실행될 때는 호스트명 및 IP 탐색을 통해 환경(`dev` 또는 `server`)을 자동 판별할 수 있습니다.
   - 하지만 격리된 도커 컨테이너 내부에서는 호스트 OS의 고유 호스트명이나 물리 IP에 접근하지 못하므로, 명시적인 `TDMS_ENV` 환경 변수 없이는 `unknown`으로 반환됩니다.
2. **도커 컴포즈 기본값 폴백 및 Python load_dotenv 미덮어쓰기**:
   - `docker-compose.yml` 파일 내부에서 `TDMS_ENV=${TDMS_ENV:-dev}` 처리가 적용되어 있었습니다.
   - 호스트 환경에 `TDMS_ENV`가 명시되어 있지 않은 상태로 도커 컴포즈 빌드 및 기동을 실행할 경우, 기본 폴백 값인 `'dev'`가 환경변수로 주입됩니다.
   - 격리된 컨테이너 내에서 구동되는 파이썬 앱(`EnvDetector` 및 `config.py`)은 마운트된 `/app/.env` 파일을 `load_dotenv()`를 통해 읽어오지만, **`dotenv` 라이브러리의 기본 설정(`override=False`)**에 따라 이미 시스템 환경변수로 선언된 `TDMS_ENV`를 `.env` 파일에 기록된 값(예: `TDMS_ENV=server`)으로 덮어쓰지 못하고 무시하는 결함이 존재했습니다. 이로 인해 마운트된 `.env`에서 `TDMS_ENV=server`로 직접 수정해도 컨테이너 내부는 항상 `dev`로 오인하게 되었습니다.

## 3. 해결책
1. **코드 수준에서의 선택적 환경변수 오버라이드 구현**:
   - `tdms_core/p1_shared/p1_shared/utils/env_detector.py` 및 관련 설정에서 `dotenv_values()`를 사용하여 `.env` 파일에 실제로 값이 입력되어 있는(공백이나 빈 값이 아닌) 변수들을 `os.environ`에 명시적으로 주입(오버라이드)하도록 보완했습니다.
   ```python
   # env_detector.py
   env_file = find_dotenv()
   if env_file:
       # .env 파일의 값을 읽음 (비어있지 않은 실제 명시된 값만 환경변수로 오버라이드 주입)
       vals = dotenv_values(env_file)
       for k, v in vals.items():
           if v is not None and v.strip() != "":
               os.environ[k] = v
   # 그 외 누락되었거나 비어 있는 키들은 기본 load_dotenv로 폴백 로드
   load_dotenv(find_dotenv())
   ```
2. **설정 모듈 동기화**:
   - `tdms_core/p3_usdms/config.py` 파일의 로드부에도 `load_dotenv(find_dotenv(), override=True)`를 지정하여 설정 로딩 단계에서도 `.env` 수정사항이 확실히 반영되도록 조치했습니다.
3. **서버 PC 로컬 `.env` 명시적 설정 반영**:
   - 서버 PC의 로컬 `.env` 파일에 `TDMS_ENV=server`를 입력하고, 서버 PC에서 `docker compose up -d --build`를 통해 컨테이너들을 재생성하였습니다.

## 4. 검증 결과
- 수정 후 `pytest` 유닛 테스트를 재가동하여 `conftest.py` 모킹 조건 및 로컬 환경 검증 테스트가 모두 통과함을 확인했습니다.
- 이제 서버 PC의 컨테이너를 재빌드 및 재기동하더라도, 마운트된 `.env`에 정의된 `TDMS_ENV=server`를 무시하지 않고 최우선적으로 오버라이드 반영하여 **"서버 PC (운영계)"**로 환경을 완벽하게 자동 식별합니다.
