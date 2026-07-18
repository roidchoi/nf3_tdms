# [DEC-009] Docker Container Log Directory Force Binding

## Status
- **상태**: Approved ✅
- **결정일**: 2026-07-17
- **작성자**: Antigravity

---

## 1. 맥락 (Context)
- `p1_shared`에 위치한 `EnvDetector`가 `.env` 파일을 로딩하면서, 환경변수 오버라이드로 인해 도커 컴포즈에서 설정한 `LOG_DIR=/app/logs` 값이 `.env` 내의 정적 로컬 디렉토리 경로인 `LOG_DIR=./logs`로 무조건 덮어쓰여지고 있었음.
- 이로 인해 도커 컨테이너 실행 환경에서 로그와 실행 결과 JSON 파일들이 볼륨 마운트 영역 바깥으로 어긋나게 떨어져서 이력이 유실되고 컨테이너가 내려갈 시 영구 소멸하는 문제가 발생.
- 기존 공통 모듈의 덮어쓰기 로직을 전역으로 고칠 경우, 로컬 호스트 및 동기화 스크립트 등 `.env` 우선권을 전제로 구현되어 작동 중이던 기존 아키텍처에 예측할 수 없는 전역 부작용(Side Effect)을 줄 위험성이 매우 높았음.

---

## 2. 결정 사항 (Decision)
- **최소 침습적 고립 아키텍처 적용**:
  1. 공통 환경 변수 감지 유틸리티(`EnvDetector`)는 수정을 가하지 않고 원상태 그대로 둔다.
  2. 대신, 도커 컨테이너에서 동작하는 각 서브프로젝트(`p3_usdms`, `p2_kdms`)의 `config.py` 내 설정 클래스 생성자(`__init__`) 레벨에서 도커 컨테이너 여부를 감지하여, 볼륨 마운트용 디렉토리 경로를 명시적으로 보정/강제한다.
  3. `LOG_DIR` 경로만 도커 내부일 때 `/app/logs`로 정밀 강제 설정함으로써 공통 `EnvDetector` 덮어쓰기로 인한 버그를 안전하게 우회하도록 한다.

---

## 3. 구현 내용 (Implementation)
- `tdms_core/p3_usdms/config.py` 파일의 `Settings` 클래스 내부에 적용:
  ```python
  def __init__(self, **values):
      super().__init__(**values)
      if not self.SEC_USER_AGENT:
          raise ValueError("SEC_USER_AGENT 환경변수가 누락되었습니다")

      # 도커 환경 감지 후 강제 지정
      import os
      if os.path.exists('/.dockerenv'):
          self.LOG_DIR = "/app/logs"
  ```

---

## 4. 결과 및 영향 (Consequences)
- **장점**:
  - `EnvDetector` 수정으로 인해 발생할 수 있는 다른 서비스 및 스크립트에서의 부작용을 사전에 100% 원천 차단함.
  - 도커 컨테이너 볼륨 마운트가 정상 동작하여 로그 소실 문제가 완벽히 해소됨.
- **단점**:
  - 도커 환경 전용 강제 설정 코드가 각 서브프로젝트(`config.py`)에 중복으로 존재하게 됨. 단, 로깅 구조의 차이(KDMS는 `log_dir`, USDMS는 `LOG_DIR`)가 있었기에 개별 설정 파일에서 명시적으로 처리하는 것이 훨씬 제어하기 유연함.

---
## 관련 엔티티
- [[p3_usdms_wiki/errors/usdms-err-007_container_log_vol_loss_and_permission_denied]]
- [[p2_kdms_wiki/decisions/dec-010_container_log_directory_force_binding]]
