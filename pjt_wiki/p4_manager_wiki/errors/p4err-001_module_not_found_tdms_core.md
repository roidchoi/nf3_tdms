---
id: P4ERR-001
sub_project: p4_manager
severity: high
status: confirmed
last_seen: Task-002
related: [[p4_manager_wiki/environment]]
---

# [P4ERR-001] 도커 백엔드 기동 시 모듈 임포트 실패 (ModuleNotFoundError: No module named 'tdms_core')

### 발생 패턴 및 재현 조건
- **환경**: Docker Compose 환경 (python:3.12-slim 베이스 이미지)
- **발생 시점**: `docker-compose up -d` 기동 시 `p4_backend` 컨테이너가 무한 재시작 루프에 빠짐.
- **재현 방법**:
  1. `docker-compose -f tdms_core/p4_manager/docker-compose.yml up --build -d` 실행
  2. `docker ps` 확인 시 `p4_backend` 상태가 `Restarting`으로 나타남.

### 실제 에러 로그 (요약 금지)
```text
Traceback (most recent call last):
  File "/usr/local/bin/uvicorn", line 10, in <module>
    sys.exit(main())
             ^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 1524, in __call__
    return self.main(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 1445, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 1308, in invoke
    return ctx.invoke(self.callback, **ctx.params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/click/core.py", line 877, in invoke
    return callback(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/uvicorn/main.py", line 441, in main
    run(
  File "/usr/local/lib/python3.12/site-packages/uvicorn/main.py", line 609, in run
    config.load_app()
  File "/usr/local/lib/python3.12/site-packages/uvicorn/config.py", line 415, in load_app
    return import_from_string(self.app)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/site-packages/uvicorn/importer.py", line 22, in import_from_string
    raise exc from None
  File "/usr/local/lib/python3.12/site-packages/uvicorn/importer.py", line 19, in import_from_string
    module = importlib.import_module(module_str)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.12/importlib/__init__.py", line 90, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1387, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1360, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1331, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 935, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 999, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File "/app/tdms_core/p4_manager/main.py", line 6, in <module>
    from tdms_core.p4_manager.config import settings
ModuleNotFoundError: No module named 'tdms_core'
```

### 원인
- `backend.Dockerfile` 빌드 및 구동 시 파이썬 작업 디렉토리(WORKDIR)는 `/app/tdms_core/p4_manager` 로 기재되어 있습니다.
- `main.py` 내부에서 `from tdms_core.p4_manager.config import settings` 와 같이 상위 `tdms_core` 패키지를 참조하는 임포트문이 선언되어 있으나, 시스템 파이썬 `sys.path` 에 상위 루트 디렉토리 `/app` 이 등록되어 있지 않아 하위 모듈이 `tdms_core`를 찾지 못하고 크래시가 났던 것입니다.

### 해결법 (필수)
- **해결 절차**:
  1. `tdms_core/p4_manager/backend.Dockerfile` 내부에 환경변수 `ENV PYTHONPATH="/app"`을 명시적으로 선언해 줍니다.
- **수정된 코드** (`tdms_core/p4_manager/backend.Dockerfile`):
```dockerfile
# uv 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uv/bin/uv
ENV PATH="/uv/bin:${PATH}"
ENV PYTHONPATH="/app"
```

### 발생 이력
- Task-002 구현 후 Docker 통합 빌드 테스트 중 최초 발견 및 조치.
