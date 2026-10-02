"""
Kavach — Weather Provider Retry Logic
======================================
Simple exponential backoff retry for transient network failures.
"""
import time
import logging
from typing import Callable, TypeVar, Optional
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
):
    """
    Retry decorator with exponential backoff.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay after each attempt
        max_delay: Maximum delay between retries
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        logger.warning(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    
                    logger.debug(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
                    delay = min(delay * backoff_factor, max_delay)
            
            # Should never reach here, but for type safety
            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic failed unexpectedly")
        
        return wrapper
    return decorator


def quick_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Quick retry decorator for network operations (3 attempts, 1s initial delay)."""
    return retry_with_backoff(max_attempts=3, initial_delay=1.0, backoff_factor=2.0)(func)
