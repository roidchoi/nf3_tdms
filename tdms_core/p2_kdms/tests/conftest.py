# tests/conftest.py

import pytest

@pytest.fixture(autouse=True)
def mock_lifespan(mocker):
    """
    모든 테스트에서 FastAPI의 lifespan(DB 커넥션 풀 생성 및 StartupValidator 검증)을 
    오프라인에서 안전하게 우회하도록 모킹합니다.
    """
    mocker.patch("main.create_kdms_pool")
    mocker.patch("p2_kdms.main.create_kdms_pool")
    mocker.patch("main.BackupManager")
    mocker.patch("p2_kdms.main.BackupManager")
    
    mock_val1 = mocker.patch("main.StartupValidator")
    mock_val2 = mocker.patch("p2_kdms.main.StartupValidator")
    
    report = mocker.MagicMock()
    report.is_healthy = True
    
    mock_val1.return_value.validate.return_value = report
    mock_val2.return_value.validate.return_value = report

