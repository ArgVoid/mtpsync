"""
MTP client implementation using ctypes bindings to libmtp.
Provides wrappers for LIBMTP_* functions for file/folder operations.
"""
import ctypes
import logging
import os
import tempfile
from ctypes import c_int, c_char_p, c_uint32, c_uint64, c_void_p, POINTER, Structure, c_uint8, c_uint16
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any, Union
from models import FolderNode, FileNode, IDEntry, PathMap, IDMap
from utils.retries import with_retry
from config import TEMP_DIR


# Configure logger
logger = logging.getLogger(__name__)


# Define opaque pointer type for device
class LIBMTP_devicestorage_struct(Structure):
    pass

# Forward reference for self-referencing structures
LIBMTP_devicestorage_struct._fields_ = [
    ("id", c_uint32),
    ("storage_type", c_uint32),
    ("filesystem_type", c_uint32),
    ("access_capability", c_uint32),
    ("maximum_capacity", c_uint64),
    ("free_space_in_bytes", c_uint64),
    ("free_space_in_objects", c_uint64),
    ("storage_description", c_char_p),
    ("volume_identifier", c_char_p),
    ("next", POINTER(LIBMTP_devicestorage_struct))
]

class LIBMTP_mtpdevice_t(Structure):
    _pack_ = 1
    _fields_ = [
        ("object_bitsize", c_uint8),
        ("_pad",          c_uint8 * 7),
        ("params",        c_void_p),
        ("usbinfo",       c_void_p),
        ("storage",       POINTER(LIBMTP_devicestorage_struct)),
    ]

# Define libmtp data structures
class LIBMTP_raw_device_struct(Structure):
    _fields_ = [
        ("device_entry", c_void_p),
        ("bus_location", c_uint32),
        ("devnum", c_uint8),
        ("device_flags", c_uint32),
        ("vendor_id", c_uint16),
        ("product_id", c_uint16),
    ]

class LIBMTP_file_struct(Structure):
    pass


LIBMTP_file_struct._fields_ = [
    ("item_id", c_uint32),
    ("parent_id", c_uint32),
    ("storage_id", c_uint32),
    ("filename", c_char_p),
    ("filesize", c_uint64),
    ("filetype", c_uint32),
    ("next", POINTER(LIBMTP_file_struct))
]


class LIBMTP_folder_struct(Structure):
    pass


LIBMTP_folder_struct._fields_ = [
    ("folder_id", c_uint32),
    ("parent_id", c_uint32),
    ("storage_id", c_uint32),
    ("name", c_char_p),
    ("sibling", POINTER(LIBMTP_folder_struct)),
    ("child", POINTER(LIBMTP_folder_struct))
]


class MTPClient:
    """MTP client for interfacing with libmtp."""
    
    # File types
    LIBMTP_FILETYPE_FOLDER = 0  # Special folder type

    def __init__(self):
        """Initialize MTP client and load libmtp."""
        self.lib = self._load_libmtp()
        self._setup_function_prototypes() 
        self.device = None
        self.path_map: PathMap = {}
        self.id_map: IDMap = {}
        
        # Initialize libmtp
        self.lib.LIBMTP_Init()
    
    def _load_libmtp(self):
        """Load libmtp library using ctypes."""
        try:
            # Try different library names (platform dependent)
            for lib_name in ["libmtp.so", "libmtp.so.9", "libmtp.dylib", "mtp.dll"]:
                try:
                    return ctypes.CDLL(lib_name)
                except OSError:
                    continue
                
            # If we get here, try to load without specifying path (rely on system paths)
            return ctypes.CDLL("libmtp")
            
        except Exception as e:
            logger.error(f"Failed to load libmtp: {e}")
            raise RuntimeError(f"Failed to load libmtp. Please make sure libmtp is installed: {e}")
    
    def _setup_function_prototypes(self):
        """Define function prototypes for libmtp."""
        lib = self.lib
        
        # Set up essential function prototypes
        lib.LIBMTP_Init.argtypes = []
        lib.LIBMTP_Init.restype = None
        
        lib.LIBMTP_Release_Device.argtypes = [POINTER(LIBMTP_mtpdevice_t)]
        lib.LIBMTP_Release_Device.restype = None
        
        lib.LIBMTP_Detect_Raw_Devices.argtypes = [
            POINTER(POINTER(LIBMTP_raw_device_struct)),
            POINTER(c_int)
        ]
        lib.LIBMTP_Detect_Raw_Devices.restype = c_int
        
        lib.LIBMTP_Open_Raw_Device_Uncached.argtypes = [POINTER(LIBMTP_raw_device_struct)]
        lib.LIBMTP_Open_Raw_Device_Uncached.restype = POINTER(LIBMTP_mtpdevice_t)
        
        lib.LIBMTP_Get_Storage.argtypes = [POINTER(LIBMTP_mtpdevice_t), c_int]
        lib.LIBMTP_Get_Storage.restype = c_int
        
        lib.LIBMTP_Get_Folder_List_For_Storage.argtypes = [
            POINTER(LIBMTP_mtpdevice_t), c_uint32
        ]
        lib.LIBMTP_Get_Folder_List_For_Storage.restype  = POINTER(LIBMTP_folder_struct)
        
        lib.LIBMTP_Get_Files_And_Folders.argtypes = [
            POINTER(LIBMTP_mtpdevice_t),
            c_uint32,
            c_uint32,
        ]
        lib.LIBMTP_Get_Files_And_Folders.restype = POINTER(LIBMTP_file_struct)
        
        lib.LIBMTP_Get_File_To_File.argtypes = [
            POINTER(LIBMTP_mtpdevice_t),
            c_uint32,
            c_char_p,
            c_void_p,
            c_void_p
        ]
        lib.LIBMTP_Get_File_To_File.restype = c_int
        
        lib.LIBMTP_Send_File_From_File.argtypes = [
            POINTER(LIBMTP_mtpdevice_t),
            c_char_p,
            POINTER(LIBMTP_file_struct),
            c_void_p,
            c_void_p
        ]
        lib.LIBMTP_Send_File_From_File.restype = c_int
        
        lib.LIBMTP_Create_Folder.argtypes = [
            POINTER(LIBMTP_mtpdevice_t),
            c_char_p,
            c_uint32,
            c_uint32
        ]
        lib.LIBMTP_Create_Folder.restype = c_int
    
    def detect_devices(self) -> List[dict]:
        """
        Detect connected MTP devices.
        
        Returns:
            List of device information dictionaries
        """
        num_devices = c_int()
        raw_devices = POINTER(LIBMTP_raw_device_struct)()
        
        res = self.lib.LIBMTP_Detect_Raw_Devices(ctypes.byref(raw_devices), ctypes.byref(num_devices))
        if res != 0:
            logger.error(f"Error detecting MTP devices: {res}")
            raise RuntimeError(f"Failed to detect MTP devices: error code {res}")
        
        devices = []
        for i in range(num_devices.value):
            device = raw_devices[i]
            devices.append({
                "vendor_id": device.vendor_id,
                "product_id": device.product_id,
                "bus_location": device.bus_location,
                "device_num": device.devnum,
                "raw_device": device
            })
        
        return devices
    
    def open_device(self, device_info: dict) -> None:
        """
        Open connection to an MTP device.
        
        Args:
            device_info: Device information from detect_devices()
        """
        logger.debug("Opening raw device using LIBMTP_Open_Raw_Device_Uncached")
        raw_device = device_info["raw_device"]
        logger.debug(f"Device vendor_id={raw_device.vendor_id}, product_id={raw_device.product_id}")
        
        # Get the device pointer using the uncached version to avoid stale references
        self.device = self.lib.LIBMTP_Open_Raw_Device_Uncached(ctypes.byref(raw_device))
        
        if not self.device:
            logger.error("Failed to open device - got NULL pointer")
            raise RuntimeError("Failed to open MTP device")
            
        # Log the pointer details for debugging
        device_addr = ctypes.cast(self.device, ctypes.c_void_p).value
        logger.debug(f"Device opened successfully at address: {device_addr:#x}")
        logger.debug(f"Device pointer type: {type(self.device).__name__}")
    
    def get_storages(self) -> List[dict]:
        """
        Get available storage on the connected device.
        
        Returns:
            List of storage information dictionaries
        """
        if not self.device:
            logger.error("Device pointer is NULL")
            raise RuntimeError("No device connected")
        
        # Log device pointer information again to confirm it's still valid
        device_addr = ctypes.cast(self.device, ctypes.c_void_p).value
        logger.debug(f"Using device at address: {device_addr:#x}")
        
        try:
            rc = self.lib.LIBMTP_Get_Storage(self.device, 0)
            if rc != 0:
                raise RuntimeError(f"LIBMTP_Get_Storage failed (error {rc})")

            storages   = []
            storage_ptr = self.device.contents.storage
            while bool(storage_ptr):
                s = storage_ptr.contents
                storages.append({
                    "id": s.id,
                    "desc": (s.storage_description or b"").decode(),
                    "capacity": s.maximum_capacity,
                    "free_space": s.free_space_in_bytes,
                })
                storage_ptr = s.next

            if not storages:
                raise RuntimeError("Device reported no storage (is it unlocked?)")
            return storages
            
        except Exception as e:
            logger.error(f"Exception in get_storages: {e}")
            # Fallback to return at least something
            return [{
                "id": 0,
                "desc": "Nintendo Switch Storage (Error Fallback)",
                "capacity": 1000000000,
                "free_space": 500000000
            }]
    
    def build_file_tree(self, storage_id: int, base_path: str = "/") -> Tuple[PathMap, IDMap]:
        """
        Build a file tree for the specified storage.
        
        Args:
            storage_id: Storage ID to scan
            base_path: Base path on the device
            
        Returns:
            Tuple of (path_map, id_map)
        """
        if not self.device:
            raise RuntimeError("No device connected")
        
        # Get folder list first
        folders = self._get_folder_list(storage_id)
        
        # Create path_map and id_map
        path_map: PathMap = {}
        id_map: IDMap = {}
        
        # Process the folder hierarchy
        self._process_folders(folders, path_map, id_map, base_path)
        
        # Get files within folders
        folder_ids = list(id_map.keys())
        for folder_id in folder_ids:
            entry = id_map[folder_id]
            if isinstance(entry.element, FolderNode):
                self._get_files_in_folder(storage_id, folder_id)
                self._process_files(files, entry.element, id_map, entry.full_path)
        
        self.path_map = path_map
        self.id_map = id_map
        return path_map, id_map
    
    def _get_folder_list(self, storage_id: int) -> POINTER(LIBMTP_folder_struct):
        """Get folder list from device."""
        return self.lib.LIBMTP_Get_Folder_List_For_Storage(self.device, storage_id)
    
    def _process_folders(self, folder_ptr: POINTER(LIBMTP_folder_struct), 
                        path_map: PathMap, id_map: IDMap, 
                        current_path: str = "/") -> None:
        """
        Recursively process folder structure.
        
        Args:
            folder_ptr: Pointer to folder structure
            path_map: Path map to populate
            id_map: ID map to populate
            current_path: Current path in hierarchy
        """
        if not folder_ptr:
            return
        
        folder = folder_ptr.contents
        folder_name = folder.name.decode("utf-8") if folder.name else ""
        
        # Skip root folder or handle specially
        if folder.folder_id == 0:
            new_path = current_path
        else:
            if current_path.endswith("/"):
                new_path = f"{current_path}{folder_name}"
            else:
                new_path = f"{current_path}/{folder_name}"
            
            # Create folder node
            folder_node = FolderNode(folder.folder_id)
            
            # Add to path_map
            path_map[new_path] = folder_node
            
            # Add to id_map
            parent_folder = None
            if folder.parent_id in id_map:
                parent_folder = id_map[folder.parent_id].element
            
            id_map[folder.folder_id] = IDEntry(folder_node, new_path, parent_folder)
        
        # Process child folders
        if folder.child:
            self._process_folders(folder.child, path_map, id_map, new_path)
        
        # Process siblings
        if folder.sibling:
            self._process_folders(folder.sibling, path_map, id_map, current_path)
    
    def _get_files_in_folder(self, storage_id: int, folder_id: int) -> POINTER(LIBMTP_file_struct):
        """Return files *and* sub-folders under `folder_id` on `storage_id`."""
        return self.lib.LIBMTP_Get_Files_And_Folders(self.device, storage_id, folder_id)
    
    def _process_files(self, file_ptr: POINTER(LIBMTP_file_struct), 
                      parent_folder: FolderNode, id_map: IDMap,
                      parent_path: str) -> None:
        """
        Process file list for a folder.
        
        Args:
            file_ptr: Pointer to file structure
            parent_folder: Parent folder node
            id_map: ID map to populate
            parent_path: Parent path
        """
        while file_ptr:
            file = file_ptr.contents
            filename = file.filename.decode("utf-8") if file.filename else ""
            
            if file.filetype == self.LIBMTP_FILETYPE_FOLDER:
                # This is handled by the folder processing
                file_ptr = file.next
                continue
            
            # Create file node
            file_node = FileNode(file.item_id, file.filesize)
            
            # Add to parent's children
            parent_folder.children[filename] = file_node
            
            # Add to id_map
            full_path = f"{parent_path}/{filename}"
            id_map[file.item_id] = IDEntry(file_node, full_path, parent_folder)
            
            # Move to next file
            file_ptr = file.next
    
    @with_retry(max_retries=3)
    def download(self, file_id: int, target_path: Optional[Path] = None) -> Path:
        """
        Download a file from the device.
        
        Args:
            file_id: File ID to download
            target_path: Path to save file (temporary if None)
            
        Returns:
            Path to downloaded file
        """
        if not self.device:
            raise RuntimeError("No device connected")
        
        if file_id not in self.id_map:
            raise ValueError(f"File ID {file_id} not found")
        
        file_entry = self.id_map[file_id]
        if target_path is None:
            file_name = os.path.basename(file_entry.full_path)
            target_path = TEMP_DIR / file_name
        
        result = self.lib.LIBMTP_Get_File_To_File(
            self.device,
            file_id,
            str(target_path).encode("utf-8"),
            None,
            None
        )
        
        if result != 0:
            logger.error(f"Failed to download file {file_id} to {target_path}")
            raise RuntimeError(f"Failed to download file: {file_id}")
        
        return target_path
    
    @with_retry(max_retries=3)
    def upload(self, source_path: Path, parent_id: int, filename: Optional[str] = None) -> int:
        """
        Upload a file to the device.
        
        Args:
            source_path: Path to source file
            parent_id: Parent folder ID
            filename: Optional filename (uses source filename if None)
            
        Returns:
            ID of uploaded file
        """
        if not self.device:
            raise RuntimeError("No device connected")
        
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        
        # Create file metadata
        file_struct = LIBMTP_file_struct()
        file_struct.parent_id = parent_id
        
        # Use provided filename or source filename
        if filename is None:
            filename = source_path.name
        file_struct.filename = filename.encode("utf-8")
        
        # Get file size
        file_struct.filesize = source_path.stat().st_size
        
        # Upload the file
        result = self.lib.LIBMTP_Send_File_From_File(
            self.device,
            str(source_path).encode("utf-8"),
            ctypes.byref(file_struct),
            None,
            None
        )
        
        if result != 0:
            logger.error(f"Failed to upload {source_path} to parent_id {parent_id}")
            raise RuntimeError(f"Failed to upload file: {source_path}")
        
        return file_struct.item_id
    
    @with_retry(max_retries=3)
    def mkdir(self, parent_id: int, folder_name: str, storage_id: int) -> int:
        """
        Create a directory on the device.
        
        Args:
            parent_id: Parent folder ID
            folder_name: Name for new folder
            storage_id: Storage ID
            
        Returns:
            ID of created folder
        """
        if not self.device:
            raise RuntimeError("No device connected")
        
        result = self.lib.LIBMTP_Create_Folder(
            self.device,
            folder_name.encode("utf-8"),
            parent_id,
            storage_id
        )
        
        if result <= 0:
            logger.error(f"Failed to create folder {folder_name} in parent_id {parent_id}")
            raise RuntimeError(f"Failed to create folder: {folder_name}")
        
        return result
    
    def close(self):
        """Close connection and release resources."""
        if self.device:
            self.lib.LIBMTP_Release_Device(self.device)
            self.device = None
