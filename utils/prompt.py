"""
Utility for handling user interaction prompts.
"""
import sys
from typing import List, Dict, Any, Optional, TypeVar, Union


T = TypeVar('T')


def prompt_choice(
    message: str, 
    options: List[T], 
    display_func: Optional[callable] = None
) -> T:
    """
    Prompt user to select from a list of options.
    
    Args:
        message: Message to display to user
        options: List of options to choose from
        display_func: Optional function to convert option to display string
        
    Returns:
        Selected option
    """
    if not options:
        raise ValueError("No options provided for selection")
    
    if display_func is None:
        display_func = str
    
    print(f"\n{message}")
    for i, option in enumerate(options, 1):
        print(f"  {i}. {display_func(option)}")
    
    while True:
        try:
            choice = input("\nEnter choice number: ")
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return options[idx]
            print(f"Please enter a number between 1 and {len(options)}")
        except ValueError:
            print("Please enter a valid number")
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user")
            sys.exit(1)


def prompt_yes_no(message: str, default: bool = False) -> bool:
    """
    Prompt user for a yes/no response.
    
    Args:
        message: Message to display to user
        default: Default response if user just presses Enter
        
    Returns:
        True for yes, False for no
    """
    default_prompt = "[y/N]" if not default else "[Y/n]"
    prompt_str = f"{message} {default_prompt}: "
    
    while True:
        try:
            response = input(prompt_str).strip().lower()
            
            if not response:
                return default
                
            if response.startswith('y'):
                return True
                
            if response.startswith('n'):
                return False
                
            print("Please enter 'yes' or 'no'")
        
        except (KeyboardInterrupt, EOFError):
            print("\nOperation cancelled by user")
            sys.exit(1)


def display_progress(current: int, total: int, message: str = "", width: int = 50) -> None:
    """
    Display a simple progress bar in the terminal.
    
    Args:
        current: Current progress value
        total: Total value for 100% completion
        message: Optional message to display with the progress bar
        width: Width of the progress bar in characters
    """
    progress = min(1.0, current / total if total > 0 else 1.0)
    filled_width = int(width * progress)
    bar = '█' * filled_width + '-' * (width - filled_width)
    percent = progress * 100
    
    sys.stdout.write(f"\r{message} [{bar}] {percent:.1f}% ({current}/{total})")
    sys.stdout.flush()
    
    if current >= total:
        sys.stdout.write('\n')
