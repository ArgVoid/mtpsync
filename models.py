"""
Models for MTP Directory Synchronization Service.
Contains path_map and id_map data structure definitions.
"""
from typing import Dict, Union, Literal, Optional


class FileNode:
    """Represents a file in the path_map structure."""
    
    def __init__(self, id: int, size: int):
        self.id: int = id
        self.type: Literal["file"] = "file"
        self.size: int = size


class FolderNode:
    """Represents a folder in the path_map structure."""
    
    def __init__(self, id: int):
        self.id: int = id
        self.type: Literal["folder"] = "folder"
        self.children: Dict[str, Union["FolderNode", FileNode]] = {}


class IDEntry:
    """Entry in the id_map structure."""
    
    def __init__(self, element: Union[FolderNode, FileNode], full_path: str, parent: Optional[FolderNode] = None):
        self.element: Union[FolderNode, FileNode] = element
        self.full_path: str = full_path
        self.parent: Optional[FolderNode] = parent


# Type definitions for the main data structures
PathMap = Dict[str, FolderNode]
IDMap = Dict[int, IDEntry]
