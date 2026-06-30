# tdms_core/p4_manager/tests/test_infra.py
import os
import pytest
import subprocess
import time
import requests
from fastapi.testclient import TestClient

# 아직 main.py가 없거나 비어 있을 것이므로, 
# 테스트 실행 단계에서 ImportError가 발생하는 것이 Red 상태를 의미합니다.
try:
    from tdms_core.p4_manager.main import app
    client = TestClient(app)
except ImportError:
    client = None

def test_p4_backend_health_check_returns_ok():
    """
    [목적] p4 FastAPI 자체 헬스체크 API가 정상적으로 {"status": "ok"}를 반환하는지 확인
    [유도] main.py에 /api/mgr/health GET 라우트가 정의되어야 함
    """
    if client is None:
        pytest.fail("tdms_core.p4_manager.main.app 임포트 실패 (구현되지 않음)")
    response = client.get("/api/mgr/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "p4_backend"}

def test_nginx_config_exists_and_contains_rules():
    """
    [목적] nginx.conf 설정 파일이 정확히 생성되었고 핵심 프록시 문구가 포함되어 있는지 확인
    [유도] 지정된 경로에 nginx.conf가 존재하고 Upgrade 헤더 등의 키워드가 파싱되어야 함
    """
    # 루트 workspace 기준 상대 경로 검사
    config_path = "nginx/nginx.conf"
    if not os.path.exists(config_path):
        # 만약 테스트 실행 위치가 tdms_core/p4_manager 라면 그 기준의 상대 경로 검사
        config_path = "nginx/nginx.conf"
        
    # 절대 경로 확보
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "nginx", "nginx.conf")
    
    assert os.path.exists(config_path), f"Nginx 설정 파일이 존재하지 않습니다: {config_path}"
    
    with open(config_path, "r") as f:
        content = f.read()
        
    assert "proxy_pass http://$upstream_kdms:8000" in content
    assert "proxy_pass http://$upstream_usdms:8005" in content
    assert "proxy_pass http://$upstream_p4:8010" in content
    assert "Upgrade $http_upgrade" in content

@pytest.mark.integration
def test_docker_compose_up_and_nginx_routing():
    """
    [목적] docker-compose up 실행 후 Nginx 포트 80을 통해 p4 백엔드 헬스체크까지 정상 리버스 프록시되는지 통합 검증
    [실행 조건] Docker Daemon 및 tdms-net 가동 필요
    [유도] docker-compose.yml에 정의된 p4_frontend/nginx 바인딩 포트(80)를 통해 http://localhost:80/api/mgr/health를 호출했을 때 ok 반환
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compose_path = os.path.join(base_dir, "docker-compose.yml")
    
    assert os.path.exists(compose_path), f"Docker Compose 파일이 존재하지 않습니다: {compose_path}"

    # docker-compose up 실행
    compose_cmd = ["docker-compose", "-f", compose_path, "up", "--build", "-d"]
    subprocess.run(compose_cmd, check=True)
    
    # 컨테이너 기동 대기 (최대 5초)
    time.sleep(3)
    
    try:
        # Nginx 리버스 프록시를 경유하여 p4_backend 호출 테스트
        response = requests.get("http://localhost:80/api/mgr/health", timeout=3)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # status API 프록시 호출 및 오프라인 예외 격리 검증
        status_response = requests.get("http://localhost:80/api/mgr/status", timeout=3)
        assert status_response.status_code == 200
        assert "kr" in status_response.json()
        assert "us" in status_response.json()
    finally:
        # 테스트 종료 후 컨테이너 자동 소멸 처리 (클린업)
        down_cmd = ["docker-compose", "-f", compose_path, "down"]
        subprocess.run(down_cmd, check=True)
