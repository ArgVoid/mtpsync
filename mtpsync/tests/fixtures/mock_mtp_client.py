"""
Mock MTP client for testing.
"""
import os
import tempfile
from pathlib import Path

from mtpsync.models import FolderNode, FileNode, IDEntry, PathMap, IDMap


class MockMTPClient:
    """Mock MTP client for testing the sync engine."""
    
    def __init__(self):
        """Initialize mock MTP client with empty maps."""
        self.path_map = {}
        self.id_map = {}
        self.next_id = 1000
        self.downloads = {}  # Mapping of file_id to content
        self.uploads = {}    # Mapping of parent_id to {filename: content}
        self.created_folders = {}  # Mapping of parent_id to folder names
    
    def add_folder(self, path: str, parent_id: int = 0) -> int:
        """Add a folder to the mock structure."""
        folder_id = self.next_id
        self.next_id += 1
        
        folder_node = FolderNode(folder_id)
        self.path_map[path] = folder_node
        
        parent = None
        if parent_id in self.id_map:
            parent = self.id_map[parent_id].element
        
        self.id_map[folder_id] = IDEntry(folder_node, path, parent)
        
        # Update parent's children
        if parent_id in self.id_map:
            parent_entry = self.id_map[parent_id]
            if isinstance(parent_entry.element, FolderNode):
                folder_name = os.path.basename(path.rstrip("/"))
                parent_entry.element.children[folder_name] = folder_node
        
        return folder_id
    
    def add_file(self, path: str, size: int, parent_id: int, content: bytes = None) -> int:
        """Add a file to the mock structure."""
        file_id = self.next_id
        self.next_id += 1
        
        file_node = FileNode(file_id, size)
        
        # Store the file content for later download
        if content is not None:
            self.downloads[file_id] = content
        
        # Get parent folder for children update
        parent = None
        if parent_id in self.id_map:
            parent = self.id_map[parent_id].element
        
        # Add to id_map
        self.id_map[file_id] = IDEntry(file_node, path, parent)
        
        # Update parent's children
        if parent_id in self.id_map and isinstance(parent, FolderNode):
            filename = os.path.basename(path)
            parent.children[filename] = file_node
        
        return file_id
    
    def download(self, file_id: int, target_path: Path = None) -> Path:
        """Mock download operation."""
        if file_id not in self.id_map:
            raise ValueError(f"File ID {file_id} not found")
        
        if file_id not in self.downloads:
            raise RuntimeError(f"No content available for file ID {file_id}")
        
        # Create a temporary file with the stored content
        if target_path is None:
            fd, temp_path = tempfile.mkstemp()
            os.close(fd)
            target_path = Path(temp_path)
        
        with open(target_path, "wb") as f:
            f.write(self.downloads[file_id])
        
        return target_path
    
    def upload(self, source_path: Path, parent_id: int, filename: str = None) -> int:
        """Mock upload operation."""
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        if parent_id not in self.id_map:
            raise ValueError(f"Parent ID {parent_id} not found")
        
        if filename is None:
            filename = source_path.name
        
        # Read source file content
        with open(source_path, "rb") as f:
            content = f.read()
        
        # Store upload information
        if parent_id not in self.uploads:
            self.uploads[parent_id] = {}
        self.uploads[parent_id][filename] = content
        
        # Create file node
        parent_entry = self.id_map[parent_id]
        parent_path = parent_entry.full_path
        file_path = f"{parent_path}/{filename}"
        file_size = source_path.stat().st_size
        
        return self.add_file(file_path, file_size, parent_id, content)
    
    def mkdir(self, parent_id: int, folder_name: str, storage_id: int) -> int:
        """Mock directory creation."""
        if parent_id not in self.id_map:
            raise ValueError(f"Parent ID {parent_id} not found")
        
        # Store created folder
        if parent_id not in self.created_folders:
            self.created_folders[parent_id] = []
        self.created_folders[parent_id].append(folder_name)
        
        # Create folder node
        parent_entry = self.id_map[parent_id]
        parent_path = parent_entry.full_path
        folder_path = f"{parent_path}/{folder_name}"
        if not folder_path.endswith("/"):
            folder_path += "/"
        
        return self.add_folder(folder_path, parent_id)
    
    def close(self):
        """Mock close operation (no-op)."""
        pass
