# Task-001 Walkthrough: 개발 환경 및 인프라 구축 완료 보고서

*   **Sub Project**: p4_manager
*   **기준 Spec**: [task-001_spec.md](file:///home/roid2/pjt/nf3/01_nf3_tdms/docs/p4_manager/tasks/task-001_spec.md)
*   **완료일**: 2026-06-08
*   **검증 결과**: ALL PASSED (3개 테스트 통과)

---

## 1. 구현 사양 대조 및 준수 여부 검증

본 Task에서 요구된 모든 설계 사양과 파일 구성 요소를 정밀 검토한 결과, 누락 없이 100% 완벽히 이행되었음을 확인했습니다.

| 요구 설계 영역 | 상세 사양 및 파일 | 구현 및 검증 결과 | 준수 여부 |
|---|---|---|---|
| **개발 환경 구성** | `requirements.txt`<br>`pyproject.toml` | - fastapi, uvicorn, requests, pytest 등의 가상환경 구성<br>- 공유 라이브러리 `p1_shared` 상대 경로 editable install 완료<br>- `p4_manager` 패키지 자체 editable install 완료 | **준수 (100%)** |
| **백엔드 스케줄 스켈레톤** | `tdms_core/p4_manager/main.py` | - FastAPI `/api/mgr/health` GET 라우터 구현<br>- 반환 규격 `{"status": "ok", "service": "p4_backend"}` 준수 | **준수 (100%)** |
| **Nginx 리버스 프록시** | `tdms_core/p4_manager/nginx/nginx.conf` | - `/api/kr/` -> `p2_kdms:8000`<br>- `/api/us/` -> `p3_usdms:8005`<br>- `/api/mgr/` -> `p4_backend:8010`<br>- `/ws/logs/kr` 및 `/ws/logs/us` WebSocket 중계 선언 완료<br>- `/` 프론트엔드 SPA fallback 서빙 구성 | **준수 (100%)** |
| **컨테이너 이미지 빌드** | `backend.Dockerfile`<br>`frontend.Dockerfile` | - `backend`: Python 3.12-slim 기반, uv 툴체인을 활용하여 시스템 python에 editable 연동 패키지 주입<br>- `frontend`: Nginx 1.25 기반, MVP용 Stub index.html 포함 구성 | **준수 (100%)** |
| **멀티 컨테이너 정의** | `docker-compose.yml` | - `p4_backend` (포트 8010 노출)<br>- `p4_frontend` (호스트 포트 80 바인딩, `depends_on: p4_backend`) 구성<br>- 외부 네트워크 `tdms-net` 연동 사양 충족 | **준수 (100%)** |
| **TDD 검증 테스트** | `tests/test_infra.py` | - Tier 1 단위 테스트 (Nginx 설정 정적 분석)<br>- Tier 2 격리 통합 테스트 (FastAPI API 단독 호출)<br>- Tier 3 실제 통합 테스트 (docker-compose 구동 및 리프록시 통신) | **준수 (100%)** |

---

## 2. 주요 개선 및 최적화 사항 (설계적 판단)

1.  **Nginx 기동 차단 버그 근본적 해결 (Dynamic Upstream Resolve)**
    *   *문제점*: 통합 테스트 기동 시점이나 실 운영 초기 단계에서 다른 백엔드 컨테이너(`p2_kdms`, `p3_usdms`)가 아직 구동되지 않았을 경우, Nginx가 upstream host를 찾지 못하고 크래시가 발생하는 현상이 관찰되었습니다.
    *   *해결책*: Nginx에 도커 내장 DNS 리졸버(`resolver 127.0.0.11 valid=10s;`)를 부여하고 `set` 지시어로 호스트명을 변수화하여 프록시 패스를 수행하도록 설정을 개정했습니다. 이로써 기동 순서에 무관하게 항상 안전하게 부팅되도록 인프라를 안정화했습니다.
    *   *우회 조치*: Nginx의 `rewrite` 지시어 뒤에 `break`가 들어갈 경우 `set` 지시어가 무시되는 특성을 고려하여, `set` 선언을 `rewrite`보다 위로 올리는 선행 정렬을 완벽하게 구현하여 500 에러 현상을 해소했습니다.
2.  **대용량 빌드 컨텍스트 경량화 (`.dockerignore`)**
    *   *문제점*: 프로젝트 루트에서 docker-compose 빌드를 할 때 대용량 데이터 폴더(`data/`, `backups/`)와 에이전트 자산(`.agents/`), 문서(`docs/`, `pjt_wiki/`) 등이 함께 도커 데몬에 업로드되는 현상이 발견되었습니다.
    *   *해결책*: [.dockerignore](file:///home/roid2/pjt/nf3/01_nf3_tdms/.dockerignore) 파일을 정교하게 정의하여 코드가 아닌 모든 문서 및 데이터 폴더를 배제함으로써 컨테이너 빌드 속도를 비약적으로 단축하고 빌드 크기를 최적화하였습니다.

---

## 3. 테스트 실행 결과 요약

### 3.1. 단위 및 통합 테스트 성공 로그
```text
$ conda run -n tdms_p4_env env PYTHONPATH=. pytest tdms_core/p4_manager/tests/ -v --run-integration

============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0 -- /home/roid2/miniforge3/envs/tdms_p4_env/bin/python3
cachedir: .pytest_cache
rootdir: /home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager
configfile: pyproject.toml
plugins: anyio-4.13.0, mock-3.15.1, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 3 items

tdms_core/p4_manager/tests/test_infra.py::test_p4_backend_health_check_returns_ok PASSED [ 33%]
tdms_core/p4_manager/tests/test_infra.py::test_nginx_config_exists_and_contains_rules PASSED [ 66%]
tdms_core/p4_manager/tests/test_infra.py::test_docker_compose_up_and_nginx_routing PASSED [100%]

============================== 3 passed in 14.82s ==============================
```

### 3.2. 수동 라우팅 통신 테스트 (Nginx 경유 API 헬스체크)
```text
$ curl -v http://localhost:80/api/mgr/health

* Host localhost:80 was resolved.
* Connected to localhost (::1) port 80
> GET /api/mgr/health HTTP/1.1
> Host: localhost
> User-Agent: curl/8.5.0
> 
< HTTP/1.1 200 OK
< Server: nginx/1.25.5
< Date: Mon, 08 Jun 2026 09:05:22 GMT
< Content-Type: application/json
< Content-Length: 38
< Connection: keep-alive
< 
{"status":"ok","service":"p4_backend"}
```

이로써 T-001 개발 환경 및 인프라 구축 Task는 완벽하게 완료되었습니다.
