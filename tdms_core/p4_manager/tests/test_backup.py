# tdms_core/p4_manager/tests/test_backup.py
import pytest
from fastapi.testclient import TestClient
from tdms_core.p4_manager.main import app

client = TestClient(app)

def test_get_env_returns_correct_profile_for_dev(mocker):
    """
    [목적] /api/mgr/env API 호출 시 EnvDetector가 감지한 'dev' 환경 프로파일을 정상 리턴하는지 검증
    [유도] EnvDetector.detect()가 "dev"를 반환할 때 {"env": "dev"}를 JSON으로 응답하게 유도
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    response = client.get("/api/mgr/env")
    assert response.status_code == 200
    assert response.json()["env"] == "dev"


def test_post_backup_on_server_raises_403_forbidden(mocker):
    """
    [목적] 서버 PC 환경에서 백업 API 호출 시, I/O 및 오제어 차단을 위해 403 Forbidden과 경고 문구가 리턴되는지 검증
    [유도] EnvDetector.detect()가 "server"를 리턴할 시 403 HTTP 예외를 발생시키고 지정된 에러 메시지를 넘기도록 유도
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="server")
    response = client.post("/api/mgr/backup?market=kdms&tag=manual")
    assert response.status_code == 403
    assert "서버 PC는 로컬 스냅샷 백업" in response.json()["detail"]


def test_post_backup_on_dev_success(mocker, tmp_path):
    """
    [목적] 개발 PC 환경에서 백업 API를 트리거했을 때, 실제로 물리 디렉토리를 압축하여 스냅샷 파일을 보관소에 생성하는지 검증
    [유도] 
      - EnvDetector.detect() -> "dev" 모킹
      - config의 BACKUP_BASE_DIR를 임시 tmp_path로 세팅
      - subprocess.run을 모킹하여 tar 압축이 성공적으로 실행(returncode=0)되었음을 흉내 내며, 테스트 내에서 스냅샷 파일 실물을 생성
    """
    mocker.patch("p1_shared.utils.env_detector.EnvDetector.detect", return_value="dev")
    
    # 임시 백업 보관 디렉토리 생성 및 설정 오버라이드
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    mocker.patch("tdms_core.p4_manager.config.settings.BACKUP_BASE_DIR", str(backup_dir))
    mocker.patch("tdms_core.p4_manager.config.settings.data_path", str(tmp_path / "data"))
    
    # 임시 소스 데이터 폴더 생성
    (tmp_path / "data" / "kdms_db").mkdir(parents=True)
    (tmp_path / "data" / "usdms_db").mkdir(parents=True)

    # tar 명령 실행 시 실제 파일이 생성되는 것처럼 mock 처리
    def mock_tar_exec(*args, **kwargs):
        from pathlib import Path
        cmd = args[0]
        # .tar.gz로 끝나는 경로 요소를 찾음
        backup_file_path = next((x for x in cmd if isinstance(x, str) and x.endswith(".tar.gz")), None)
        if backup_file_path:
            Path(backup_file_path).parent.mkdir(exist_ok=True, parents=True)
            Path(backup_file_path).write_bytes(b"dummy_tar_content")
        
        # subprocess.run의 성공 응답 리턴
        mock_process = mocker.Mock()
        mock_process.returncode = 0
        return mock_process

    mocker.patch("subprocess.run", side_effect=mock_tar_exec)

    # API 실행
    response = client.post("/api/mgr/backup?market=kdms&tag=manual")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert "physical_checkpoint_" in res_data["filename"]
    assert (backup_dir / "kdms" / "manual" / res_data["filename"]).exists()


def test_get_backup_list_success(mocker, tmp_path):
    """
    [목적] 로컬 스냅샷 디렉토리에 존재하는 tar.gz 파일 목록을 파싱하여 생성일시 및 용량 정보를 담은 이력 리스트를 반환하는지 검증
    [유도] 지정된 디렉토리의 파일들을 rglob하여 BackupInfo 규격의 JSON 배열로 올바르게 변환하게 유도
    """
    backup_dir = tmp_path / "backups"
    manual_dir = backup_dir / "manual"
    manual_dir.mkdir(parents=True)
    
    # 더미 백업 파일 생성
    dummy_file = manual_dir / "physical_checkpoint_20260610_113000.tar.gz"
    dummy_file.write_bytes(b"dummy_tar_content")
    
    mocker.patch("tdms_core.p4_manager.config.settings.BACKUP_BASE_DIR", str(backup_dir))
    
    response = client.get("/api/mgr/backup/list")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["filename"] == "physical_checkpoint_20260610_113000.tar.gz"
    assert data[0]["tag"] == "manual"
    assert data[0]["size_bytes"] == len(b"dummy_tar_content")
    assert data[0]["verified"] is True


@pytest.mark.integration
def test_real_physical_backup_generation_on_dev(tmp_path):
    """
    [목적] 모킹 없이 실제 개발 PC(WSL2) 환경에서 로컬 DB 볼륨 디렉토리를 압축하여 physical_checkpoint_*.tar.gz가 정상 빌드되는지 실물 검증
    [설명] 66GB에 달하는 실물 DB 압축 지연을 방지하기 위해, 설정 상의 데이터 경로를 임시 경로로 우회하여 
           실물 tar 명령어의 구동 및 백업 생성 파이프라인 전체를 신속하게 검증합니다.
    """
    from pathlib import Path
    from tdms_core.p4_manager.config import settings
    
    # 원래 설정 백업
    orig_data_path = settings.data_path
    orig_backup_dir = settings.BACKUP_BASE_DIR
    
    # 임시 검증용 경로 설정 및 더미 데이터 디렉토리 구축
    test_data_dir = tmp_path / "data"
    test_backup_dir = tmp_path / "backups"
    
    (test_data_dir / "kdms_db").mkdir(parents=True)
    (test_data_dir / "usdms_db").mkdir(parents=True)
    (test_data_dir / "kdms_db" / "dummy.txt").write_text("dummy kdms data")
    (test_data_dir / "usdms_db" / "dummy.txt").write_text("dummy usdms data")
    
    # 글로벌 싱글톤 설정 임시 전환 (모킹 라이브러리 미사용)
    settings.data_path = str(test_data_dir)
    settings.BACKUP_BASE_DIR = str(test_backup_dir)
    
    try:
        # 1. 백업 실행 API 기동 (실물 tar 가동)
        response = client.post("/api/mgr/backup?market=kdms&tag=integration_test")
        
        # 서버 PC 환경인 경우 403 Forbidden 단언
        env_resp = client.get("/api/mgr/env")
        current_env = env_resp.json()["env"]
        
        if current_env == "server":
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            res_data = response.json()
            assert res_data["status"] == "success"
            
            # 2. 실제 아카이브 파일 생성 및 크기 검증
            backup_file_path = Path(res_data["path"])
            assert backup_file_path.exists()
            assert backup_file_path.stat().st_size > 0
            
            # 3. 이력 목록 조회 API 연동 확인
            list_resp = client.get("/api/mgr/backup/list")
            assert list_resp.status_code == 200
            list_data = list_resp.json()
            assert any(b["filename"] == res_data["filename"] for b in list_data)
    finally:
        # 원래 설정 원복 (부작용 방지)
        settings.data_path = orig_data_path
        settings.BACKUP_BASE_DIR = orig_backup_dir

