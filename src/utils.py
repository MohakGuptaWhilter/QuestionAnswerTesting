"""
Utility functions for the QA Testing system.
"""

import os
from pathlib import Path


def ensure_directory_exists(directory_path: str) -> str:
    """
    Ensure that a directory exists, creating it if necessary.
    
    Args:
        directory_path: Path to the directory
        
    Returns:
        The directory path
    """
    os.makedirs(directory_path, exist_ok=True)
    return directory_path


def get_project_root() -> Path:
    """
    Get the root directory of the project.
    
    Returns:
        Path object pointing to project root
    """
    return Path(__file__).parent.parent


def check_file_exists(file_path: str) -> bool:
    """
    Check if a file exists.
    
    Args:
        file_path: Path to the file
        
    Returns:
        True if file exists, False otherwise
    """
    return os.path.isfile(file_path)


def get_file_size(file_path: str) -> int:
    """
    Get the size of a file in bytes.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File size in bytes, or -1 if file doesn't exist
    """
    try:
        return os.path.getsize(file_path)
    except Exception:
        return -1


def create_sample_data_structure():
    """
    Create sample directory structure for testing.
    """
    project_root = get_project_root()
    
    directories = [
        project_root / "data" / "input",
        project_root / "data" / "output",
        project_root / "data" / "test"
    ]
    
    for directory in directories:
        ensure_directory_exists(str(directory))
    
    return project_root
