"""
Unit tests for utils/checksum.py
"""
import hashlib
import os
import tempfile
from pathlib import Path
import pytest

from utils.checksum import (
    calculate_checksum, 
    calculate_checksum_from_fileobj,
    batch_calculate_checksums
)


@pytest.fixture
def test_file():
    """Fixture to create a temporary test file with known content."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content for checksum verification")
    yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def multiple_test_files():
    """Fixture to create multiple temporary test files."""
    files = []
    for i in range(3):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(f"test content {i}".encode("utf-8"))
        files.append(Path(f.name))
    
    yield files
    
    for file in files:
        os.unlink(file)


def test_calculate_checksum_md5(test_file):
    """Test MD5 checksum calculation."""
    expected_hash = hashlib.md5(b"test content for checksum verification").hexdigest()
    calculated_hash = calculate_checksum(test_file, algorithm="md5")
    
    assert calculated_hash == expected_hash


def test_calculate_checksum_sha256(test_file):
    """Test SHA-256 checksum calculation."""
    expected_hash = hashlib.sha256(b"test content for checksum verification").hexdigest()
    calculated_hash = calculate_checksum(test_file, algorithm="sha256")
    
    assert calculated_hash == expected_hash


def test_calculate_checksum_from_fileobj(test_file):
    """Test checksum calculation from file object."""
    expected_hash = hashlib.sha256(b"test content for checksum verification").hexdigest()
    
    with open(test_file, "rb") as f:
        calculated_hash = calculate_checksum_from_fileobj(f)
    
    assert calculated_hash == expected_hash


def test_calculate_checksum_from_fileobj_preserves_position(test_file):
    """Test that calculate_checksum_from_fileobj preserves file position."""
    with open(test_file, "rb") as f:
        # Read first 4 bytes and position should be at byte 4
        f.read(4)
        position = f.tell()
        
        # Calculate checksum should return to position 4
        calculate_checksum_from_fileobj(f)
        
        assert f.tell() == position


def test_batch_calculate_checksums(multiple_test_files):
    """Test parallel checksum calculation for multiple files."""
    # Calculate expected checksums
    expected_checksums = {}
    for i, file_path in enumerate(multiple_test_files):
        content = f"test content {i}".encode("utf-8")
        expected_hash = hashlib.sha256(content).hexdigest()
        expected_checksums[file_path] = expected_hash
    
    # Calculate checksums using the batch function
    result = batch_calculate_checksums(multiple_test_files)
    
    assert len(result) == len(multiple_test_files)
    for file_path in multiple_test_files:
        assert file_path in result
        assert result[file_path] == expected_checksums[file_path]
