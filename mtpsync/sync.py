"""
Core synchronization engine for MTP directory sync.
Implements Verify (Flow A) and Execute (Flow B) operations.
"""
import json
import logging
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Union, Literal

from .config import (
    DEFAULT_EXECUTION_PLAN,
    MAX_THREADS,
    DATA_DIR,
    TEMP_DIR
)
from .models import PathMap, IDMap, FolderNode, FileNode
from .mtp_client import MTPClient
from .utils.checksum import calculate_checksum, batch_calculate_checksums


# Configure logger
logger = logging.getLogger(__name__)


class SyncEngine:
    """Main synchronization engine."""

    def __init__(
        self,
        mtp_client: MTPClient,
        source_dir: Path,
        dest_path: str,
        use_checksum: bool = True,
        storage_id: int = 0
    ):
        """
        Initialize the sync engine.
        
        Args:
            mtp_client: Connected MTP client
            source_dir: Path to source directory
            dest_path: Destination path on the device
            use_checksum: Whether to use checksums for comparison
            storage_id: MTP storage ID to use for operations
        """
        self.mtp_client = mtp_client
        self.source_dir = source_dir.resolve()
        self.dest_path = dest_path
        self.use_checksum = use_checksum
        self.storage_id = storage_id
        self.temp_dir = TEMP_DIR
        
        # Ensure paths are normalized
        if not self.dest_path.startswith("/"):
            self.dest_path = f"/{self.dest_path}"
            
        # Ensure temp dir exists
        self.temp_dir.mkdir(exist_ok=True)

    def verify(self, plan_path: Optional[Path] = None) -> Path:
        """
        Flow A: Verify differences between source and destination.
        
        Args:
            plan_path: Optional custom path for execution plan output
            
        Returns:
            Path to generated execution plan
        """
        if plan_path is None:
            plan_path = DEFAULT_EXECUTION_PLAN
        
        # Ensure directory exists
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build source and destination maps
        source_map = self._scan_source_directory()
        
        # Build execution plan
        execution_plan = {}
        
        for rel_path, entry_type in source_map.items():
            # Check if path exists in destination
            dest_full_path = os.path.normpath(f"{self.dest_path}/{rel_path}")
            
            if self._path_exists_in_dest(dest_full_path):
                # Path exists, check if content matches
                if entry_type == "file" and not self._compare_file(rel_path, dest_full_path):
                    # File exists but doesn't match (content/size different)
                    execution_plan[rel_path] = "file"
            else:
                # Path doesn't exist, add to execution plan
                execution_plan[rel_path] = entry_type
        
        # Save execution plan
        with open(plan_path, "w") as f:
            json.dump(execution_plan, f, indent=2)
        
        return plan_path

    def execute(self, plan_path: Optional[Path] = None) -> Tuple[bool, Optional[Path]]:
        """
        Flow B: Execute sync based on execution plan.
        
        Args:
            plan_path: Path to execution plan (will generate one if None)
            
        Returns:
            Tuple of (success, retry_plan_path)
        """
        # Find plan
        if plan_path is None:
            plan_path = self._find_latest_plan()
        
        # If still no plan, generate it
        if plan_path is None:
            logger.info("No execution plan found. Generating new plan.")
            plan_path = self.verify()
        
        # Load plan
        with open(plan_path, "r") as f:
            execution_plan = json.load(f)
        
        failed_entries = {}
        
        # First, create all directories
        for rel_path, entry_type in execution_plan.items():
            if entry_type == "dir":
                success = self._ensure_directory(rel_path)
                if not success:
                    failed_entries[rel_path] = entry_type
        
        # Then, create all files
        for rel_path, entry_type in execution_plan.items():
            if entry_type == "file":
                success = self._sync_file(rel_path)
                if not success:
                    failed_entries[rel_path] = entry_type
        
        # Create retry plan if needed
        if failed_entries:
            retry_plan_path = DATA_DIR / ".execution_retry" / f"{uuid.uuid4().hex}.json"
            with open(retry_plan_path, "w") as f:
                json.dump(failed_entries, f, indent=2)
            return False, retry_plan_path
        
        return True, None

    def _scan_source_directory(self) -> Dict[str, Literal["dir", "file"]]:
        """
        Scan source directory recursively.
        
        Returns:
            Dict mapping relative paths to entry types
        """
        if not self.source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {self.source_dir}")
        
        source_map = {}
        
        for root, dirs, files in os.walk(self.source_dir):
            # Calculate relative path from source_dir
            rel_root = os.path.relpath(root, self.source_dir)
            
            # Skip the root directory
            if rel_root != ".":
                # Use forward slashes and add trailing slash for directories
                rel_path = rel_root.replace("\\", "/")
                if not rel_path.endswith("/"):
                    rel_path += "/"
                    
                source_map[rel_path] = "dir"
            
            # Add all files
            for file in files:
                rel_path = os.path.join(rel_root, file).replace("\\", "/")
                # Normalize root path
                if rel_path.startswith("./"):
                    rel_path = rel_path[2:]
                    
                source_map[rel_path] = "file"
        
        return source_map

    def _path_exists_in_dest(self, full_path: str) -> bool:
        """
        Check if a path exists in destination.
        
        Args:
            full_path: Full path on the device
            
        Returns:
            True if path exists
        """
        # Check if path is in path_map
        return full_path in self.mtp_client.path_map

    def _compare_file(self, rel_path: str, dest_full_path: str) -> bool:
        """
        Compare source file with destination file.
        
        Args:
            rel_path: Relative path from source directory
            dest_full_path: Full path on the device
            
        Returns:
            True if files match
        """
        source_path = self.source_dir / rel_path
        
        # Find file node
        if dest_full_path not in self.mtp_client.path_map:
            return False
        
        file_node = self.mtp_client.path_map[dest_full_path]
        if not isinstance(file_node, FileNode):
            return False
        
        if not self.use_checksum:
            # Compare by size only
            return source_path.stat().st_size == file_node.size
        
        # Compare by checksum
        try:
            # Download the file to temp directory
            temp_path = self.mtp_client.download(file_node.id)
            
            # Calculate checksums
            src_checksum = calculate_checksum(source_path)
            dest_checksum = calculate_checksum(temp_path)
            
            # Delete temp file after comparison
            if temp_path.exists():
                temp_path.unlink()
            
            return src_checksum == dest_checksum
            
        except Exception as e:
            logger.error(f"Error comparing file {rel_path}: {e}")
            return False

    def _ensure_directory(self, rel_path: str) -> bool:
        """
        Ensure directory exists on destination.
        
        Args:
            rel_path: Relative path from source directory
            
        Returns:
            True if successful
        """
        if not rel_path.endswith("/"):
            rel_path += "/"
            
        # Build full path on device
        full_path = os.path.normpath(f"{self.dest_path}/{rel_path}")
        
        # Check if path already exists
        if full_path in self.mtp_client.path_map:
            return True
        
        # Split path into components
        path_parts = rel_path.split("/")
        if not path_parts[-1]:  # Handle trailing slash
            path_parts.pop()
            
        # Ensure parent directories exist
        current_path = self.dest_path
        current_id = 0  # Assume root ID is 0
        
        for part in path_parts:
            if not part:  # Skip empty parts
                continue
                
            next_path = f"{current_path}/{part}"
            
            if next_path in self.mtp_client.path_map:
                # Path exists, get its ID
                current_id = self.mtp_client.path_map[next_path].id
            else:
                # Create directory
                try:
                        # Use the storage ID provided during initialization
                    storage_id = self.storage_id
                    
                    # Create folder
                    new_id = self.mtp_client.mkdir(current_id, part, storage_id)
                    
                    # Update maps
                    new_folder = FolderNode(new_id)
                    self.mtp_client.path_map[next_path] = new_folder
                    
                    # Get parent folder
                    parent = None
                    if current_id in self.mtp_client.id_map:
                        parent = self.mtp_client.id_map[current_id].element
                        
                    self.mtp_client.id_map[new_id] = IDEntry(new_folder, next_path, parent)
                    
                    current_id = new_id
                    
                except Exception as e:
                    logger.error(f"Failed to create directory {next_path}: {e}")
                    return False
            
            current_path = next_path
        
        return True

    def _sync_file(self, rel_path: str) -> bool:
        """
        Sync a file to destination.
        
        Args:
            rel_path: Relative path from source directory
            
        Returns:
            True if successful
        """
        source_path = self.source_dir / rel_path
        
        if not source_path.exists():
            logger.error(f"Source file not found: {source_path}")
            return False
        
        # Get parent directory path
        parent_rel_path = os.path.dirname(rel_path)
        if parent_rel_path:
            parent_rel_path += "/"
            
        parent_dest_path = os.path.normpath(f"{self.dest_path}/{parent_rel_path}")
        
        # Ensure parent directory exists
        if not self._ensure_directory(parent_rel_path):
            logger.error(f"Failed to create parent directory {parent_rel_path}")
            return False
        
        # Get parent ID
        if parent_dest_path not in self.mtp_client.path_map:
            logger.error(f"Parent path not found in path_map: {parent_dest_path}")
            return False
            
        parent_node = self.mtp_client.path_map[parent_dest_path]
        if not isinstance(parent_node, FolderNode):
            logger.error(f"Parent path is not a folder: {parent_dest_path}")
            return False
            
        parent_id = parent_node.id
        
        try:
            # Upload file
            file_name = os.path.basename(rel_path)
            new_id = self.mtp_client.upload(source_path, parent_id, file_name)
            
            # Validate upload
            if self.use_checksum:
                temp_path = self.mtp_client.download(new_id)
                
                # Calculate checksums
                src_checksum = calculate_checksum(source_path)
                dest_checksum = calculate_checksum(temp_path)
                
                # Delete temp file after comparison
                if temp_path.exists():
                    temp_path.unlink()
                
                if src_checksum != dest_checksum:
                    logger.error(f"Checksum mismatch for {rel_path}")
                    return False
            
            # Update maps
            dest_full_path = f"{self.dest_path}/{rel_path}"
            file_node = FileNode(new_id, source_path.stat().st_size)
            
            # Update parent's children
            parent_node.children[file_name] = file_node
            
            # Update id_map
            self.mtp_client.id_map[new_id] = IDEntry(
                file_node, dest_full_path, parent_node
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync file {rel_path}: {e}")
            return False

    def _find_latest_plan(self) -> Optional[Path]:
        """
        Find the most recent execution plan.
        
        Returns:
            Path to plan file or None if not found
        """
        # Check default plan first
        if DEFAULT_EXECUTION_PLAN.exists():
            return DEFAULT_EXECUTION_PLAN
        
        # Check retry directory
        retry_dir = DATA_DIR / ".execution_retry"
        if not retry_dir.exists():
            return None
            
        plan_files = list(retry_dir.glob("*.json"))
        if not plan_files:
            return None
            
        # Return the most recently modified plan
        return max(plan_files, key=lambda p: p.stat().st_mtime)
