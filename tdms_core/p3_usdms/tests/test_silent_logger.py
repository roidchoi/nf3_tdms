import logging
from p3_usdms.utils.silent_logger import SilentLoopContext

def test_silent_loop_context_modifies_and_restores_log_levels():
    logger_name = "test_temp_silent_logger"
    logger = logging.getLogger(logger_name)
    
    # 초기 로깅 레벨 설정
    logger.setLevel(logging.INFO)
    assert logger.level == logging.INFO
    
    # SilentLoopContext 진입 시 WARNING으로 올라가는지 확인
    with SilentLoopContext([logger_name], target_level=logging.WARNING):
        assert logger.level == logging.WARNING
        
    # 탈출 후 다시 INFO로 원복되는지 확인
    assert logger.level == logging.INFO

def test_silent_loop_context_handles_exceptions_and_restores_log_levels():
    logger_name = "test_temp_exception_logger"
    logger = logging.getLogger(logger_name)
    
    logger.setLevel(logging.DEBUG)
    assert logger.level == logging.DEBUG
    
    try:
        with SilentLoopContext([logger_name], target_level=logging.ERROR):
            assert logger.level == logging.ERROR
            raise ValueError("Intentional error inside loop")
    except ValueError:
        pass
        
    # 예외가 발생하더라도 원래 DEBUG 레벨로 정상 복구되어야 함
    assert logger.level == logging.DEBUG
