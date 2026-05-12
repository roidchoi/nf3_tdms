import pytest
from unittest.mock import patch, MagicMock
from p1_shared.ops.db_sync import PhysicalSyncManager, SyncConfig

@pytest.fixture
def sync_config_pull():
    return SyncConfig(
        db_name="kdms",
        direction="pull",
        source_ip="192.168.35.97",
        target_ip="192.168.35.201",
        ssh_user="roid2",
        ssh_key_path="~/.ssh/test_key",
        data_path="/test/data"
    )

@pytest.fixture
def sync_config_push():
    return SyncConfig(
        db_name="usdms",
        direction="push",
        source_ip="192.168.35.201",
        target_ip="192.168.35.97",
        ssh_user="roid2",
        ssh_key_path="~/.ssh/test_key",
        data_path="/test/data"
    )

def test_preflight_check_validates_ssh(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, '_run_remote') as mock_remote:
        # 1. SSH 성공 케이스
        mock_res_success = MagicMock()
        mock_res_success.stdout = "SSH_OK"
        mock_remote.return_value = mock_res_success
        
        assert manager.preflight_check() is True
        mock_remote.assert_called_once_with("192.168.35.97", "echo SSH_OK")
        
        # 2. SSH 실패 케이스
        mock_remote.reset_mock()
        mock_res_fail = MagicMock()
        mock_res_fail.stdout = ""
        mock_res_fail.stderr = "Connection refused"
        mock_remote.return_value = mock_res_fail
        
        assert manager.preflight_check() is False

def test_stop_containers_generates_correct_commands(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, '_run_local') as mock_local, \
         patch.object(manager, '_run_remote') as mock_remote:
        
        manager.stop_containers()
        
        expected_cmd = "cd /home/roid2/pjt/nf3/01_nf3_tdms && docker compose stop kdms_db"
        
        mock_local.assert_called_once_with(expected_cmd)
        mock_remote.assert_called_once_with("192.168.35.97", expected_cmd)

def test_transfer_data_pipeline_commands_pull(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, '_run_local') as mock_local:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_local.return_value = mock_res
        
        assert manager.transfer_data() is True
        
        called_cmd = mock_local.call_args[0][0]
        assert "ssh -i ~/.ssh/test_key" in called_cmd
        assert "roid2@192.168.35.97" in called_cmd
        assert "sudo tar -czf - -C /test/data/kdms_db ." in called_cmd
        assert "| sudo tar -xzf - -C /test/data/kdms_db" in called_cmd

def test_transfer_data_pipeline_commands_push(sync_config_push):
    manager = PhysicalSyncManager(sync_config_push)
    
    with patch.object(manager, '_run_local') as mock_local:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_local.return_value = mock_res
        
        assert manager.transfer_data() is True
        
        called_cmd = mock_local.call_args[0][0]
        assert "sudo tar -czf - -C /test/data/usdms_db ." in called_cmd
        assert "| ssh -i ~/.ssh/test_key" in called_cmd
        assert "roid2@192.168.35.97" in called_cmd
        assert "sudo tar -xzf - -C /test/data/usdms_db" in called_cmd

def test_fix_permissions_executes_sudo_chown(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, '_run_local') as mock_local:
        manager.fix_permissions()
        # pull의 경우 로컬(개발PC)의 권한을 교정해야 함
        mock_local.assert_called_once_with("sudo chown -R 1000:1000 /test/data/kdms_db")

def test_execute_pipeline_order(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, 'preflight_check', return_value=True) as mock_preflight, \
         patch.object(manager, 'stop_containers') as mock_stop, \
         patch.object(manager, 'transfer_data', return_value=True) as mock_transfer, \
         patch.object(manager, 'fix_permissions') as mock_fix, \
         patch.object(manager, 'start_containers') as mock_start:
        
        assert manager.execute() is True
        
        # 호출 순서 검증은 MagicMock의 mock_calls 등으로 엄격하게 할 수 있으나
        # 여기서는 최소한 각 단계가 호출되었는지 확인
        mock_preflight.assert_called_once()
        mock_stop.assert_called_once()
        mock_transfer.assert_called_once()
        mock_fix.assert_called_once()
        mock_start.assert_called_once()

def test_execute_aborts_on_preflight_failure(sync_config_pull):
    manager = PhysicalSyncManager(sync_config_pull)
    
    with patch.object(manager, 'preflight_check', return_value=False) as mock_preflight, \
         patch.object(manager, 'stop_containers') as mock_stop:
        
        assert manager.execute() is False
        mock_preflight.assert_called_once()
        mock_stop.assert_not_called()
