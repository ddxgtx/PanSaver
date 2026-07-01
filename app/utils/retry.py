import time
from typing import Callable, Any, List
from loguru import logger

def retry_call(
    func: Callable[..., Any], 
    args: tuple = (), 
    kwargs: dict = None, 
    max_retries: int = 3, 
    backoffs: List[int] = [5, 15, 60]
) -> Any:
    """Invokes func with args/kwargs, retrying on recoverable errors using exponential backoff."""
    kwargs = kwargs or {}
    for attempt in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            err_str = str(e).lower()
            
            # Non-recoverable errors: immediately raise exception without retries
            non_recoverable_indicators = [
                "incorrect extraction code",
                "expired",
                "invalid",
                "cookie",
                "unauthorized",
                "verification code",
                "captcha",
                "errno: -12",
                "errno: -9",
                "errno: -6", # Token invalid
                "not log in"
            ]
            
            if any(indicator in err_str for indicator in non_recoverable_indicators):
                logger.error(f"Non-recoverable netdisk error detected: {e}. Aborting retries.")
                raise e
                
            if attempt == max_retries:
                logger.error(f"Function {func.__name__} failed after {max_retries} retries. Final error: {e}")
                raise e
                
            wait_time = backoffs[attempt] if attempt < len(backoffs) else backoffs[-1]
            logger.warning(
                f"Recoverable error in {func.__name__}: {e}. "
                f"Retrying in {wait_time}s (Attempt {attempt + 1}/{max_retries})..."
            )
            time.sleep(wait_time)
