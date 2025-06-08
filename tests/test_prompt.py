"""
Unit tests for utils/prompt.py
"""
import pytest
import io
import sys
from unittest.mock import patch

from utils.prompt import prompt_choice, prompt_yes_no, display_progress


@patch("builtins.input")
def test_prompt_choice_valid_input(mock_input):
    """Test prompt_choice with valid user input."""
    # Set up mock input to return "2"
    mock_input.return_value = "2"
    
    # Test with a list of options
    options = ["Option A", "Option B", "Option C"]
    result = prompt_choice("Choose an option:", options)
    
    assert result == "Option B"  # Index 1 (second option)
    mock_input.assert_called_once()


@patch("builtins.input")
def test_prompt_choice_invalid_then_valid_input(mock_input):
    """Test prompt_choice with invalid input followed by valid input."""
    # Set up mock input to return "invalid" then "4" (out of range) then "3"
    mock_input.side_effect = ["invalid", "4", "3"]
    
    # Test with a list of options
    options = ["Option A", "Option B", "Option C"]
    result = prompt_choice("Choose an option:", options)
    
    assert result == "Option C"  # Index 2 (third option)
    assert mock_input.call_count == 3


@patch("builtins.input")
def test_prompt_choice_with_custom_display_function(mock_input):
    """Test prompt_choice with custom display function."""
    mock_input.return_value = "1"
    
    # Test with objects and custom display function
    class TestObj:
        def __init__(self, name):
            self.name = name
    
    options = [TestObj("Object A"), TestObj("Object B")]
    display_func = lambda obj: f"Display: {obj.name}"
    
    result = prompt_choice("Choose an object:", options, display_func)
    
    assert result.name == "Object A"


@patch("builtins.input")
def test_prompt_yes_no_yes_responses(mock_input):
    """Test prompt_yes_no with various 'yes' responses."""
    for response in ["y", "Y", "yes", "YES", "Yes"]:
        mock_input.return_value = response
        result = prompt_yes_no("Proceed?", default=False)
        assert result is True


@patch("builtins.input")
def test_prompt_yes_no_no_responses(mock_input):
    """Test prompt_yes_no with various 'no' responses."""
    for response in ["n", "N", "no", "NO", "No"]:
        mock_input.return_value = response
        result = prompt_yes_no("Proceed?", default=True)
        assert result is False


@patch("builtins.input")
def test_prompt_yes_no_default_values(mock_input):
    """Test prompt_yes_no with default values."""
    # Empty input, using default=True
    mock_input.return_value = ""
    result = prompt_yes_no("Proceed?", default=True)
    assert result is True
    
    # Empty input, using default=False
    mock_input.return_value = ""
    result = prompt_yes_no("Proceed?", default=False)
    assert result is False


def test_display_progress():
    """Test display_progress function output."""
    captured_output = io.StringIO()
    sys.stdout = captured_output
    
    try:
        display_progress(5, 10, message="Processing", width=10)
        output = captured_output.getvalue()
        
        assert "Processing" in output
        assert "50.0%" in output
        assert "5/10" in output
        assert "█████-----" in output
        
    finally:
        sys.stdout = sys.__stdout__
