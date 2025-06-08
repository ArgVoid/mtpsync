"""
Integration tests for sync.py by mocking MTP client.
"""
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mtpsync.sync import SyncEngine
from mtpsync.models import FolderNode, FileNode, IDEntry
from mtpsync.tests.fixtures.mock_mtp_client import MockMTPClient
from mtpsync.tests.fixtures.constants import TEST_STORAGE_ID


@pytest.fixture
def temp_source_dir():
    """Create a temporary source directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        source_dir = Path(temp_dir) / "source"
        source_dir.mkdir()
        
        # Create test files and subdirectories
        (source_dir / "file1.txt").write_text("This is file 1")
        (source_dir / "file2.txt").write_text("This is file 2")
        
        subdir = source_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("This is file 3")
        
        nested_dir = subdir / "nested"
        nested_dir.mkdir()
        (nested_dir / "file4.txt").write_text("This is file 4")
        
        yield source_dir


@pytest.fixture
def mock_mtp_client():
    """Create a mock MTP client."""
    client = MockMTPClient()
    
    # Add root directory
    client.add_folder("/")
    
    # Add example file to root
    client.add_file("/existing_file.txt", 20, 1000, b"Existing file content")
    
    return client


def test_verify_flow(temp_source_dir, mock_mtp_client, tmp_path):
    """Test the verify flow with a mock MTP client."""
    # Set up sync engine
    sync_engine = SyncEngine(
        mtp_client=mock_mtp_client,
        source_dir=temp_source_dir,
        dest_path="/",
        use_checksum=True,
        storage_id=TEST_STORAGE_ID  # Use consistent test storage ID
    )
    
    # Execute verify flow
    plan_path = tmp_path / "test_plan.json"
    result_path = sync_engine.verify(plan_path)
    
    # Check plan was created at the expected path
    assert result_path == plan_path
    assert plan_path.exists()
    
    # Load and check plan content
    with open(plan_path) as f:
        plan = json.load(f)
    
    # Plan should contain all files and directories from source
    assert "file1.txt" in plan
    assert "file2.txt" in plan
    assert "subdir/" in plan
    assert "subdir/file3.txt" in plan
    assert "subdir/nested/" in plan
    assert "subdir/nested/file4.txt" in plan
    
    # Check file types
    assert plan["file1.txt"] == "file"
    assert plan["subdir/"] == "dir"


def test_execute_flow(temp_source_dir, mock_mtp_client, tmp_path):
    """Test the execute flow with a mock MTP client."""
    # Create a test plan
    plan_path = tmp_path / "test_plan.json"
    plan = {
        "file1.txt": "file",
        "file2.txt": "file",
        "subdir/": "dir",
        "subdir/file3.txt": "file"
    }
    
    with open(plan_path, "w") as f:
        json.dump(plan, f)
    
    # Set up sync engine
    sync_engine = SyncEngine(
        mtp_client=mock_mtp_client,
        source_dir=temp_source_dir,
        dest_path="/test_dest",
        use_checksum=True,
        storage_id=TEST_STORAGE_ID  # Use consistent test storage ID
    )
    
    # Add destination root
    root_id = mock_mtp_client.add_folder("/test_dest")
    
    # Execute plan
    success, retry_path = sync_engine.execute(plan_path)
    
    # Check success
    assert success is True
    assert retry_path is None
    
    # Verify directories were created
    assert root_id in mock_mtp_client.created_folders
    assert "subdir" in mock_mtp_client.created_folders[root_id]
    
    # Find created subdir ID
    subdir_id = None
    for file_id, entry in mock_mtp_client.id_map.items():
        if entry.full_path == "/test_dest/subdir/":
            subdir_id = file_id
            break
    
    assert subdir_id is not None
    
    # Verify files were uploaded
    assert root_id in mock_mtp_client.uploads
    assert "file1.txt" in mock_mtp_client.uploads[root_id]
    assert "file2.txt" in mock_mtp_client.uploads[root_id]
    
    assert subdir_id in mock_mtp_client.uploads
    assert "file3.txt" in mock_mtp_client.uploads[subdir_id]
    
    # Check file contents
    assert mock_mtp_client.uploads[root_id]["file1.txt"] == b"This is file 1"
    assert mock_mtp_client.uploads[subdir_id]["file3.txt"] == b"This is file 3"


def test_execute_flow_with_failures(temp_source_dir, mock_mtp_client, tmp_path):
    """Test the execute flow with simulated failures."""
    # Create a test plan
    plan_path = tmp_path / "test_plan.json"
    plan = {
        "file1.txt": "file",
        "bad_file.txt": "file",  # This file doesn't exist
        "subdir/": "dir"
    }
    
    with open(plan_path, "w") as f:
        json.dump(plan, f)
    
    # Set up sync engine
    sync_engine = SyncEngine(
        mtp_client=mock_mtp_client,
        source_dir=temp_source_dir,
        dest_path="/",
        use_checksum=True,
        storage_id=TEST_STORAGE_ID  # Use consistent test storage ID
    )
    
    # Patch _sync_file to simulate a failure for bad_file
    original_sync_file = sync_engine._sync_file
    
    def mock_sync_file(rel_path):
        if rel_path == "bad_file.txt":
            return False
        return original_sync_file(rel_path)
    
    sync_engine._sync_file = mock_sync_file
    
    # Execute plan
    success, retry_path = sync_engine.execute(plan_path)
    
    # Check operation failed and retry plan was created
    assert success is False
    assert retry_path is not None
    assert retry_path.exists()
    
    # Check retry plan contains only the failed file
    with open(retry_path) as f:
        retry_plan = json.load(f)
    
    assert "bad_file.txt" in retry_plan
    assert "file1.txt" not in retry_plan
    assert "subdir/" not in retry_plan
