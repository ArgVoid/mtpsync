"""
Utility for handling retries with exponential backoff.
"""
import time
import random
import logging
from functools import wraps
from typing import TypeVar, Callable, Any
from config import MAX_RETRIES, RETRY_BACKOFF_FACTOR

# Type variable for generic function
T = TypeVar('T')

logger = logging.getLogger(__name__)


def with_retry(
    max_retries: int = MAX_RETRIES, 
    backoff_factor: float = RETRY_BACKOFF_FACTOR,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for retry delay
        exceptions: Tuple of exceptions to catch and retry on
        
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            retry_count = 0
            last_exception = None
            
            while retry_count <= max_retries:
                try:
                    # Attempt to call the function
                    return func(*args, **kwargs)
                except exceptions as e:
                    retry_count += 1
                    last_exception = e
                    
                    if retry_count > max_retries:
                        func_name = getattr(func, '__name__', 'function')
                        logger.error(f"Max retries ({max_retries}) exceeded for {func_name}")
                        break
                    
                    # Calculate backoff delay with jitter
                    delay = backoff_factor ** retry_count + random.uniform(0, 1)
                    func_name = getattr(func, '__name__', 'function')
                    logger.warning(
                        f"Attempt {retry_count}/{max_retries} failed for {func_name}: "
                        f"{e.__class__.__name__}: {str(e)}. Retrying in {delay:.2f}s"
                    )
                    time.sleep(delay)
            
            # If we got here, all retries failed
            if last_exception:
                raise last_exception
            
            # This should not be reached, but just in case
            raise RuntimeError("Unexpected error in retry mechanism")
            
        return wrapper
    return decorator
