import pytest
import asyncio
from p1_shared.utils.retry import retry, async_retry

def test_retry_succeeds_on_first_attempt_without_sleep(mocker):
    mock_sleep = mocker.patch("time.sleep")
    
    @retry(max_attempts=3, delay_seconds=1.0)
    def always_success():
        return "ok"
        
    result = always_success()
    assert result == "ok"
    mock_sleep.assert_not_called()

def test_retry_calls_function_up_to_max_attempts_on_failure(mocker):
    mocker.patch("time.sleep")
    call_count = 0
    
    @retry(max_attempts=3, exceptions=(ValueError,))
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise ValueError("실패")
        
    with pytest.raises(ValueError):
        always_fail()
        
    assert call_count == 3

def test_retry_applies_exponential_backoff(mocker):
    mock_sleep = mocker.patch("time.sleep")
    
    @retry(max_attempts=3, delay_seconds=1.0, backoff=2.0, exceptions=(RuntimeError,))
    def always_fail():
        raise RuntimeError("fail")
        
    with pytest.raises(RuntimeError):
        always_fail()
        
    calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert calls == [1.0, 2.0]

@pytest.mark.asyncio
async def test_async_retry_succeeds_on_second_attempt(mocker):
    mocker.patch("asyncio.sleep", return_value=None)
    attempt = 0
    
    @async_retry(max_attempts=3, delay_seconds=0.0, exceptions=(IOError,))
    async def flaky():
        nonlocal attempt
        attempt += 1
        if attempt < 2:
            raise IOError("일시 오류")
        return "recovered"
        
    result = await flaky()
    assert result == "recovered"
    assert attempt == 2

def test_retry_with_max_attempts_one_does_not_retry(mocker):
    mock_sleep = mocker.patch("time.sleep")
    call_count = 0
    
    @retry(max_attempts=1, exceptions=(RuntimeError,))
    def fail_once():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("즉시 실패")
        
    with pytest.raises(RuntimeError):
        fail_once()
        
    assert call_count == 1
    mock_sleep.assert_not_called()

def test_retry_does_not_catch_unlisted_exception(mocker):
    mock_sleep = mocker.patch("time.sleep")
    
    @retry(max_attempts=3, exceptions=(ValueError,))
    def raise_type_error():
        raise TypeError("이건 재시도 안 함")
        
    with pytest.raises(TypeError):
        raise_type_error()
        
    mock_sleep.assert_not_called()
