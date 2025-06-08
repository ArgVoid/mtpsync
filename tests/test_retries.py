"""
Unit tests for utils/retries.py
"""
import pytest
from unittest.mock import Mock, patch
import time

from mtpsync.utils.retries import with_retry


def test_with_retry_success_first_attempt():
    """Test successful function execution on first attempt."""
    mock_func = Mock(return_value="success")
    decorated = with_retry(max_retries=3)(mock_func)
    
    result = decorated(1, 2, key="value")
    
    assert result == "success"
    mock_func.assert_called_once_with(1, 2, key="value")


def test_with_retry_success_after_retries():
    """Test successful function execution after a few retries."""
    # Function will fail twice, then succeed
    mock_func = Mock(side_effect=[ValueError("Error 1"), ValueError("Error 2"), "success"])
    decorated = with_retry(max_retries=3, exceptions=(ValueError,))(mock_func)
    
    # Patch sleep to avoid waiting during tests
    with patch("time.sleep") as mock_sleep:
        result = decorated()
    
    assert result == "success"
    assert mock_func.call_count == 3
    assert mock_sleep.call_count == 2  # Sleep called twice for the two retries


def test_with_retry_all_attempts_fail():
    """Test when all retry attempts fail."""
    # Function will fail on all attempts
    mock_func = Mock(side_effect=[ValueError("Error 1"), ValueError("Error 2"), 
                                   ValueError("Error 3"), ValueError("Error 4")])
    decorated = with_retry(max_retries=3, exceptions=(ValueError,))(mock_func)
    
    # Patch sleep to avoid waiting during tests
    with patch("time.sleep"):
        with pytest.raises(ValueError, match="Error 4"):
            decorated()
    
    assert mock_func.call_count == 4  # Initial + 3 retries


def test_with_retry_unhandled_exception():
    """Test when function raises an exception type not included in exceptions tuple."""
    # Function will raise a TypeError which is not in the exceptions tuple
    mock_func = Mock(side_effect=TypeError("Wrong type"))
    decorated = with_retry(max_retries=3, exceptions=(ValueError,))(mock_func)
    
    with pytest.raises(TypeError, match="Wrong type"):
        decorated()
    
    mock_func.assert_called_once()  # No retries should happen


def test_with_retry_exponential_backoff():
    """Test that exponential backoff is calculated correctly."""
    # Function will fail twice, then succeed
    mock_func = Mock(side_effect=[ValueError("Error 1"), ValueError("Error 2"), "success"])
    decorated = with_retry(
        max_retries=3, 
        backoff_factor=2, 
        exceptions=(ValueError,)
    )(mock_func)
    
    # Patch sleep to capture delay values
    with patch("time.sleep") as mock_sleep:
        decorated()
    
    # First retry: delay should be around 2^1 = 2 (plus jitter), second retry: around 2^2 = 4 (plus jitter)
    assert mock_sleep.call_count == 2
    
    # Extract first delay argument
    first_delay = mock_sleep.call_args_list[0][0][0]
    second_delay = mock_sleep.call_args_list[1][0][0]
    
    # Check backoff is exponential (within range accounting for jitter)
    assert 2.0 <= first_delay <= 3.0  # 2^1 plus 0-1 jitter
    assert 4.0 <= second_delay <= 5.0  # 2^2 plus 0-1 jitter
