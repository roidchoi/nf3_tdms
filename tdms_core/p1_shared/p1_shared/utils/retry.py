import time
import asyncio
from functools import wraps

def retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """동기 함수 전용 지수 백오프 재시도 데코레이터."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay_seconds
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator

def async_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """비동기 코루틴 전용 지수 백오프 재시도 데코레이터."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay_seconds
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise
                    if current_delay > 0:
                        await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
