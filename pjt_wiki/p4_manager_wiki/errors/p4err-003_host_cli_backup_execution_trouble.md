---
id: P4ERR-003
sub_project: p4_manager
severity: medium
status: confirmed
last_seen: Task-009
related: [[tdms_core/p4_manager/services/backup_service.py]], [[tdms_core/p4_manager/routers/manager.py]]
---

# [P4ERR-003] 로컬 호스트 CLI에서 백업 서비스 구동 시 경로 미인식 및 호출 혼선 에러

### 발생 패턴 및 재현 조건
- **환경**: WSL 2 / Ubuntu 24.04 LTS, Python 3.12, Conda 가상환경(`tdms_p4_env`)
- **발생 시점**: 개발 PC 호스트 터미널에서 FastAPI 서버를 거치지 않고, `conda run` 또는 python 셸을 통해 `backup_service` 모듈을 직접 로드해 백업을 수동 실행하고자 할 때 발생.
- **재현 방법**:
  1. `PYTHONPATH=. conda run -n tdms_p4_env python -c "from tdms_core.p4_manager.services.backup_service import BackupService; import asyncio; asyncio.run(BackupService.create_backup(market='usdms'))"` 실행 시 `TypeError: create_backup() missing 1 required positional argument: 'self'` 발생.
  2. 인스턴스화 호출 시 `FileNotFoundError: 백업 대상 데이터 디렉토리가 존재하지 않습니다: /app/data/usdms_db` 발생.
  3. API 라우터와 혼동해 `await` 비동기 대기를 수동 적용 시 `TypeError: object dict can't be used in 'await' expression` 발생.

### 실제 에러 로그 (요약 금지)
```text
# 1. self 누락 에러
TypeError: BackupService.create_backup() missing 1 required positional argument: 'self'

# 2. 경로 미인식 에러
FileNotFoundError: 백업 대상 데이터 디렉토리가 존재하지 않습니다: /app/data/usdms_db

# 3. 비동기 await 호출 에러
TypeError: object dict can't be used in 'await' expression
```

### 원인
1. **설정값 기본 경로와 호스트 경로의 불일치**: `p4_manager` 설정(`config.py`)은 기본적으로 도커 컨테이너 내부를 타깃으로 삼아 `data_path`가 `"/app/data"`로 고정되어 있습니다. 컨테이너 밖인 호스트 셸에서 해당 코드를 직접 가동하면 `/app/data` 디렉토리를 찾을 수 없어 `FileNotFoundError`가 발생합니다.
2. **싱글톤 인스턴스 미활용**: `backup_service.py`는 모듈 하단에 싱글톤 인스턴스인 `backup_service = BackupService()`를 이미 초기화해 둔 상태입니다. 클래스인 `BackupService`를 다이렉트로 임포트해 호출 시 인스턴스화가 누락되어 `self` 부족 오류가 유발됩니다.
3. **비동기 오인**: API 라우터(`routers/manager.py`) 등 상위 웹 서비스에서는 `async def` 기반으로 동작하나, 실제 로직이 수행되는 `backup_service` 내부 메서드는 일반 동기식 `def` 함수입니다. 이를 비동기 함수로 오인하여 `await` 키워드를 사용해 호출을 대기하려 할 때 파이썬 `TypeError`가 야기됩니다.

### 해결법 (필수)
- **해결 절차**:
  1. **경로 환경변수 명시**: 로컬 호스트 터미널에서 기동할 경우, 프로젝트 루트 기준의 데이터 및 백업 상대 경로(`DATA_PATH=data`, `BACKUP_BASE_DIR=backups`)를 커맨드 라인 인라인 환경변수로 명시하여 설정을 오버라이드해야 합니다.
  2. **싱글톤 인스턴스 임포트**: `BackupService` 클래스 원본 대신 모듈 하단에 초기화된 `backup_service` 인스턴스를 가져옵니다.
  3. **비동기 래퍼 제거**: `async/await`나 `asyncio.run`을 걷어내고, 일반 동기 함수로 직접 호출하여 사용합니다.

- **올바른 CLI 실행 명령어**:
```bash
DATA_PATH=data BACKUP_BASE_DIR=backups PYTHONPATH=. conda run -n tdms_p4_env python -c "
from tdms_core.p4_manager.services.backup_service import backup_service
res = backup_service.create_backup(market='usdms', tag='manual')
print('백업 성공 여부:', res)
"
```

### 발생 이력
- Task-009 고도화 및 실제 백업 수행 시 수동 검증 과정에서 발생
