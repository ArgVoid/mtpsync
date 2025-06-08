"""
Unit tests for models.py
"""
import pytest
from models import FolderNode, FileNode, IDEntry


def test_file_node_creation():
    """Test creating a FileNode with correct attributes."""
    file_node = FileNode(id=123, size=1024)
    
    assert file_node.id == 123
    assert file_node.size == 1024
    assert file_node.type == "file"


def test_folder_node_creation():
    """Test creating a FolderNode with correct attributes."""
    folder_node = FolderNode(id=456)
    
    assert folder_node.id == 456
    assert folder_node.type == "folder"
    assert folder_node.children == {}


def test_folder_node_children():
    """Test adding children to a FolderNode."""
    parent_folder = FolderNode(id=789)
    child_folder = FolderNode(id=101)
    child_file = FileNode(id=102, size=2048)
    
    # Add children
    parent_folder.children["subfolder"] = child_folder
    parent_folder.children["file.txt"] = child_file
    
    assert len(parent_folder.children) == 2
    assert parent_folder.children["subfolder"].id == 101
    assert parent_folder.children["subfolder"].type == "folder"
    assert parent_folder.children["file.txt"].id == 102
    assert parent_folder.children["file.txt"].size == 2048


def test_id_entry_creation():
    """Test creating an IDEntry with correct attributes."""
    folder = FolderNode(id=111)
    file = FileNode(id=222, size=512)
    
    folder_entry = IDEntry(element=folder, full_path="/path/to/folder", parent=None)
    file_entry = IDEntry(element=file, full_path="/path/to/folder/file.txt", parent=folder)
    
    # Test folder entry
    assert folder_entry.element is folder
    assert folder_entry.full_path == "/path/to/folder"
    assert folder_entry.parent is None
    
    # Test file entry
    assert file_entry.element is file
    assert file_entry.full_path == "/path/to/folder/file.txt"
    assert file_entry.parent is folder


def test_nested_folder_structure():
    """Test creating a nested folder structure with files."""
    # Create root folder
    root = FolderNode(id=1)
    
    # Create subdirectories
    docs = FolderNode(id=2)
    images = FolderNode(id=3)
    
    # Create files
    doc1 = FileNode(id=4, size=1000)
    doc2 = FileNode(id=5, size=2000)
    img1 = FileNode(id=6, size=3000)
    
    # Build structure
    root.children["docs"] = docs
    root.children["images"] = images
    docs.children["doc1.txt"] = doc1
    docs.children["doc2.txt"] = doc2
    images.children["img1.jpg"] = img1
    
    # Verify structure
    assert len(root.children) == 2
    assert "docs" in root.children
    assert "images" in root.children
    assert len(root.children["docs"].children) == 2
    assert len(root.children["images"].children) == 1
    assert root.children["docs"].children["doc1.txt"].size == 1000
    assert root.children["images"].children["img1.jpg"].size == 3000
