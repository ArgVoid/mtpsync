"""
Utility for calculating file checksums.
"""
import hashlib
from pathlib import Path
from typing import Literal, BinaryIO, Optional
import concurrent.futures
from ..config import CHECKSUM_ALGORITHM, MAX_THREADS


def calculate_checksum(
    file_path: Path,
    algorithm: Literal["md5", "sha256"] = CHECKSUM_ALGORITHM,
    buffer_size: int = 65536,
) -> str:
    """
    Calculate checksum for a file.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm to use ("md5" or "sha256")
        buffer_size: Size of chunks to read
        
    Returns:
        Hexadecimal string of the calculated hash
    """
    hash_func = hashlib.md5() if algorithm == "md5" else hashlib.sha256()
    
    with open(file_path, "rb") as f:
        return _calculate_hash(f, hash_func, buffer_size)


def calculate_checksum_from_fileobj(
    fileobj: BinaryIO,
    algorithm: Literal["md5", "sha256"] = CHECKSUM_ALGORITHM,
    buffer_size: int = 65536,
) -> str:
    """
    Calculate checksum from a file-like object.
    
    Args:
        fileobj: File-like object in binary mode
        algorithm: Hash algorithm to use ("md5" or "sha256")
        buffer_size: Size of chunks to read
        
    Returns:
        Hexadecimal string of the calculated hash
    """
    hash_func = hashlib.md5() if algorithm == "md5" else hashlib.sha256()
    original_position = fileobj.tell()
    fileobj.seek(0)
    
    try:
        return _calculate_hash(fileobj, hash_func, buffer_size)
    finally:
        # Restore original position
        fileobj.seek(original_position)


def _calculate_hash(file_obj: BinaryIO, hash_func, buffer_size: int) -> str:
    """
    Helper function to calculate hash from a file object
    """
    while True:
        data = file_obj.read(buffer_size)
        if not data:
            break
        hash_func.update(data)
            
    return hash_func.hexdigest()


def batch_calculate_checksums(file_paths: list[Path]) -> dict[Path, str]:
    """
    Calculate checksums for multiple files in parallel using thread pool.
    
    Args:
        file_paths: List of file paths to process
        
    Returns:
        Dictionary mapping file paths to their checksums
    """
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_path = {
            executor.submit(calculate_checksum, path): path 
            for path in file_paths
        }
        
        for future in concurrent.futures.as_completed(future_to_path):
            path = future_to_path[future]
            try:
                results[path] = future.result()
            except Exception as e:
                # Log the error but continue with other files
                results[path] = None
                
    return results
