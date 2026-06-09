# Task-001: 개발 환경 및 인프라 구축

> **Sub Project**: p4_manager
> **PRD 근거**: 인프라 요구사항 (Docker, tdms-net, Nginx 리버스 프록시)
> **작성일**: 2026-06-08
> **의존 Task**: 없음

---

## [위키 선조회 완료]

| 확인 항목 | 출처 파일 | 상태 |
|---|---|---|
| 외부 네트워크명 (`tdms-net`) | `pjt_wiki/p1_shared_wiki/environment.md` | ✅ 확인 |
| 백엔드 포트 번호 (`8000`, `8005`) | `pjt_wiki/p2_kdms_wiki/environment.md`, `pjt_wiki/p3_usdms_wiki/environment.md` | ✅ 확인 |
| Nginx 라우팅 포트 (`8010`) | `docs/p4_manager/p4_manager_PRD.md` | ✅ 확인 |
| Nginx 설정 파일 (`nginx.conf`) | 이 Task에서 최초 설계 | 🆕 신규 |
| Docker Compose 구조 | 이 Task에서 최초 설계 | 🆕 신규 |

---

## § 1. 목표

p4_manager 서비스를 로컬 격리 네트워크(`tdms-net`) 하에 멀티 컨테이너(Nginx, 백엔드, 프론트엔드)로 성공적으로 구동하고, 백엔드 리버스 프록시 및 WebSocket 중계 기능이 올바르게 구성되도록 인프라를 확립한다.

**구현 범위:**
- **IN**: 
  - `tdms_core/p4_manager/docker-compose.yml`
  - `tdms_core/p4_manager/backend.Dockerfile` 및 `tdms_core/p4_manager/frontend.Dockerfile`
  - `tdms_core/p4_manager/nginx/nginx.conf`
  - FastAPI 백엔드 스케줄을 수용할 스켈레톤 `main.py`
  - Nginx 설정 구문 분석 및 로컬 프록시 테스트 코드
- **OUT**: 
  - 대시보드 UI 컴포넌트 실물 구현
  - 상태 집계 서비스 비동기 비즈니스 로직 구현

---

## § 2. 구현 대상

### 신규 생성 파일
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/docker-compose.yml` — Compose 환경 정의
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/backend.Dockerfile` — FastAPI 백엔드 빌드 정의
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/frontend.Dockerfile` — Nginx + Vue 빌드 정의 (스텁 빌드)
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/nginx/nginx.conf` — Nginx 리버스 프록시 및 WS 중계 설정
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/main.py` — 백엔드 기본 진입점 및 헬스 체크
- `/home/roid2/pjt/nf3/01_nf3_tdms/tdms_core/p4_manager/tests/test_infra.py` — 인프라 구성 검증 테스트

---

## § 3. 핵심 인터페이스

구현 Agent는 아래 스켈레톤 인터페이스를 통과하도록 패키지를 구성합니다.

```python
# [신규 정의 — 이 Task에서 최초 설계]
# tdms_core/p4_manager/main.py

from fastapi import FastAPI

app = FastAPI(title="P4 Manager Backend")

@app.get("/api/mgr/health")
def health_check():
    """
    p4 백엔드 상태를 반환하는 기본 헬스 체크 엔드포인트
    """
    return {"status": "ok", "service": "p4_backend"}
```

### Nginx 라우팅 매핑 규칙
```nginx
# [신규 정의 — tdms_core/p4_manager/nginx/nginx.conf]
# 포트 80 수신
server {
    listen 80;
    
    # 1. KDMS 백엔드 라우팅 (p2)
    location /api/kr/ {
        proxy_pass http://p2_kdms:8000/api/;
    }
    
    # 2. USDMS 백엔드 라우팅 (p3)
    location /api/us/ {
        proxy_pass http://p3_usdms:8005/api/;
    }
    
    # 3. Manager 백엔드 라우팅 (p4)
    location /api/mgr/ {
        proxy_pass http://p4_backend:8010/api/mgr/;
    }
    
    # 4. WebSocket 로그 중계 (KR / US)
    location /ws/logs/kr {
        proxy_pass http://p2_kdms:8000/ws/logs;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
    
    location /ws/logs/us {
        proxy_pass http://p3_usdms:8005/ws/logs;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
    }
    
    # 5. 프론트엔드 SPA 정적 서빙 및 SPA 라우팅
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }
}
```

---

## § 4. 테스트 케이스

### 4.1 정상 동작 케이스 (Tier 2)

```python
# [Tier 2 — 격리 통합]
# tdms_core/p4_manager/tests/test_infra.py
from fastapi.testclient import TestClient
from tdms_core.p4_manager.main import app

client = TestClient(app)

def test_p4_backend_health_check_returns_ok():
    """
    [목적] p4 FastAPI 자체 헬스체크 API가 정상적으로 {"status": "ok"}를 반환하는지 확인
    [유도] main.py에 /api/mgr/health GET 라우트가 정의되어야 함
    """
    response = client.get("/api/mgr/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "p4_backend"}
```

### 4.2 경계값 및 예외 케이스 (Tier 1)

```python
# [Tier 1 — 단위]
import os

def test_nginx_config_exists_and_contains_rules():
    """
    [목적] nginx.conf 설정 파일이 정확히 생성되었고 핵심 프록시 문구가 포함되어 있는지 확인
    [유도] 지정된 경로에 nginx.conf가 존재하고 Upgrade 헤더 등의 키워드가 파싱되어야 함
    """
    config_path = "tdms_core/p4_manager/nginx/nginx.conf"
    assert os.path.exists(config_path)
    
    with open(config_path, "r") as f:
        content = f.read()
        
    assert "proxy_pass http://p2_kdms:8000" in content
    assert "proxy_pass http://p3_usdms:8005" in content
    assert "proxy_pass http://p4_backend:8010" in content
    assert "Upgrade $http_upgrade" in content
```

### 4.3 실제 통합 케이스 (Tier 3)

```python
# [Tier 3 — 실제 통합: pytest --run-integration 으로만 실행]
import pytest
import subprocess
import time
import requests

@pytest.mark.integration
def test_docker_compose_up_and_nginx_routing():
    """
    [목적] docker-compose up 실행 후 Nginx 포트 80을 통해 p4 백엔드 헬스체크까지 정상 리버스 프록시되는지 통합 검증
    [실행 조건] Docker Daemon 및 tdms-net 가동 필요
    [유도] docker-compose.yml에 정의된 p4_frontend/nginx 바인딩 포트(80)를 통해 http://localhost:80/api/mgr/health를 호출했을 때 ok 반환
    """
    # docker-compose up 실행
    compose_cmd = ["docker-compose", "-f", "tdms_core/p4_manager/docker-compose.yml", "up", "-d"]
    subprocess.run(compose_cmd, check=True)
    
    # 컨테이너 기동 대기 (최대 5초)
    time.sleep(3)
    
    try:
        # Nginx 리버스 프록시를 경유하여 p4_backend 호출 테스트
        response = requests.get("http://localhost:80/api/mgr/health", timeout=3)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        # 테스트 종료 후 컨테이너 자동 소멸 처리 (클린업)
        down_cmd = ["docker-compose", "-f", "tdms_core/p4_manager/docker-compose.yml", "down"]
        subprocess.run(down_cmd, check=True)
```

### 테스트 케이스 요약

| # | 테스트명 | 계층 | 유형 | 검증 내용 |
|---|---|---|---|---|
| 1 | `test_p4_backend_health_check_returns_ok` | Tier 2 | 정상 | /api/mgr/health 엔드포인트 응답성 검증 |
| 2 | `test_nginx_config_exists_and_contains_rules` | Tier 1 | 경계 | nginx.conf 파일 위치 및 proxy 규칙 정적 검사 |
| 3 | `test_docker_compose_up_and_nginx_routing` | Tier 3 | 실제 통합 | docker-compose를 기동하여 80번 포트 Nginx 리버스 프록시 및 백엔드 연동 전 구간 검증 |

**총 3개 테스트 — 전체 통과 시 Task 완료**

---

## § 5. 구현 참고사항

- **기술 스택**: Python 3.12, FastAPI 0.110+, Nginx 1.25 (Docker Alpine), Docker Compose v2
- **외부 네트워크 바인딩**:
  ```yaml
  # docker-compose.yml 내 네트워크 참조 설정 예시
  networks:
    tdms-net:
      external: true
  ```
- **주의사항**: WS 프록시 중계 시 핸드셰이크 차단을 막기 위해 `Upgrade` 및 `Connection` 헤더 설정 누락을 주의합니다.

---

## § 6. 완료 기준

- [ ] § 4의 테스트 케이스 전체 통과 (Tier 1 + Tier 2)
- [ ] `pytest --run-integration` 실행 시 Tier 3 테스트 전체 통과
- [ ] `docs/p4_manager/p4_manager_pjt_tasks.md`의 T-001 상태를 `완료`로 업데이트
- [ ] `docs/p4_manager/task-001_walkthrough.md` 작성
