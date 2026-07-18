# [DEC-010] Docker Container Log Directory Force Binding (KDMS)

## Status
- **상태**: Approved ✅
- **결정일**: 2026-07-17
- **작성자**: Antigravity

---

## 1. 맥락 (Context)
- KDMS (`p2_kdms`) 역시 USDMS와 공통 모듈인 `EnvDetector`를 사용하고 있었기 때문에, 도커 컨테이너 기동 시 환경변수 `LOG_DIR=/app/logs`가 무력화되고 `.env` 파일의 로컬 설정값(`LOG_DIR=./logs`)으로 오버라이드되는 동일한 버그를 겪고 있었음.
- 이로 인해 KDMS 내부에서 쌓이는 실제 데일리 시세 수집 로그 등 텍스트 로그 파일(`daily_update.log`)이 볼륨 마운트 밖으로 떨어져 유실되고 있었음.
- 대시보드의 상태 정보(`task_status_cache.json`)는 마운트 폴더 내부에 정상적으로 적재되어 정상 동작하는 것처럼 보였으나, 실제 수집 문제나 배치 에러 발생 시 도커 로그 외에 영구 저장된 파일 로그를 보존할 수 없는 심각한 구조적 결함을 발견함.

---

## 2. 결정 사항 (Decision)
- **독립적 도커 환경 보정 구현**:
  1. 공통 `EnvDetector`의 덮어쓰기 로직을 전역 수정할 경우 발생할 수 있는 잠재적 위험 요소를 최소화하기 위해, KDMS 내의 개별 설정 모듈(`config.py`)에서 단독 우회 처리한다.
  2. Pydantic 설정 클래스(`Settings`)의 생성자(`__init__`) 안에서 도커 환경인지 감지하여, KDMS의 로깅 경로 변수인 `log_dir` 값을 `/app/logs`로 명시적 보정한다.

---

## 3. 구현 내용 (Implementation)
- `tdms_core/p2_kdms/config.py` 파일의 `Settings` 클래스 내부에 적용:
  ```python
  def __init__(self, **values):
      super().__init__(**values)
      # 도커 환경 감지 후 강제 지정
      import os
      if os.path.exists('/.dockerenv'):
          self.log_dir = "/app/logs"
  ```

---

## 4. 결과 및 영향 (Consequences)
- **장점**:
  - `daily_update.log` 등 KDMS의 모든 수집 프로세스 로그 파일이 정상적으로 호스트의 마운트 디렉토리(`./logs/p2_kdms/`)에 영구 저장되어 디버깅 및 감사(Auditing)가 용이해짐.
  - 전역 부작용(Side Effect)에 대한 리스크가 전혀 없음.
- **주의 사항**:
  - 호스트 상에서 도커 볼륨 마운트 시 최초 생성된 디렉토리의 소유권 권한(`root`)으로 인해 파일 접근 문제가 생길 경우, 아래 명령어로 권한을 양도받아 해결함.
    ```bash
    sudo chown -R roid2:roid2 logs/p2_kdms
    ```

---
## 관련 엔티티
- [[p3_usdms_wiki/errors/usdms-err-007_container_log_vol_loss_and_permission_denied]]
- [[p3_usdms_wiki/decisions/dec-009_container_log_directory_force_binding]]
