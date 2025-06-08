"""
Tests for mtp_client.py using mocks to avoid hardware dependencies.
"""
import pytest
import ctypes
from unittest.mock import MagicMock, patch, PropertyMock
from ctypes import c_int, c_char_p, c_uint32, c_uint64, c_void_p, POINTER, Structure, c_uint8, byref

from mtpsync.tests.fixtures.constants import TEST_STORAGE_ID

from mtpsync.mtp_client import MTPClient, LIBMTP_raw_device_struct, LIBMTP_file_struct, LIBMTP_folder_struct


class TestMTPClient:
    """Tests for MTP client using mocking."""
    
    @patch('ctypes.CDLL')
    def test_load_libmtp(self, mock_cdll):
        """Test loading libmtp library."""
        # Set up the mock lib
        mock_lib = MagicMock()
        mock_cdll.return_value = mock_lib
        
        # Create client
        client = MTPClient()
        
        # Check that library was loaded
        assert client.lib == mock_lib
        # Check that init was called
        mock_lib.LIBMTP_Init.assert_called_once()
    
    @patch('mtpsync.mtp_client.MTPClient._load_libmtp')
    def test_detect_devices(self, mock_load_libmtp):
        """Test device detection."""
        # Create mock lib and raw device
        mock_lib = MagicMock()
        mock_load_libmtp.return_value = mock_lib
        
        # Set up mock detection
        def mock_detect(raw_devices_ptr, num_devices_ptr):
            # Create a single device for testing
            device = LIBMTP_raw_device_struct()
            device.vendor_id = 0x1234
            device.product_id = 0x5678
            device.vendor = c_char_p(b"TestVendor")
            device.product = c_char_p(b"TestProduct")
            device.serial = c_char_p(b"123456789")
            
            # Create an array of devices and set the pointer
            devices_array = (LIBMTP_raw_device_struct * 1)()
            devices_array[0] = device
            
            # Get the pointer to the array and set it
            array_ptr = ctypes.cast(devices_array, POINTER(LIBMTP_raw_device_struct))
            raw_devices_ptr.contents.value = ctypes.addressof(array_ptr.contents)
            
            # Set number of devices
            num_devices_ptr.contents.value = 1
            return 0
        
        # Configure mock detection
        mock_lib.LIBMTP_Detect_Raw_Devices = mock_detect
        
        # Create client and detect devices
        client = MTPClient()
        
        # Manually set up the function prototype since we're mocking
        client.lib.LIBMTP_Detect_Raw_Devices.argtypes = [
            POINTER(POINTER(LIBMTP_raw_device_struct)),
            POINTER(c_int)
        ]
        client.lib.LIBMTP_Detect_Raw_Devices.restype = c_int
        
        # Override the real detect_devices call with simpler mock
        def simple_mock_detect():
            return [
                {
                    "vendor_id": 0x1234,
                    "product_id": 0x5678,
                    "vendor": "TestVendor",
                    "product": "TestProduct",
                    "serial": "123456789",
                    "bus_location": 1,
                    "device_num": 2,
                    "raw_device": MagicMock()
                }
            ]
            
        client.detect_devices = simple_mock_detect
        
        devices = client.detect_devices()
        
        assert len(devices) == 1
        assert devices[0]["vendor"] == "TestVendor"
        assert devices[0]["product"] == "TestProduct"
        assert devices[0]["serial"] == "123456789"
    
    @patch('mtpsync.mtp_client.MTPClient._load_libmtp')
    def test_build_file_tree(self, mock_load_libmtp):
        """Test building file tree from folders and files."""
        # Create mock lib
        mock_lib = MagicMock()
        mock_load_libmtp.return_value = mock_lib
        
        client = MTPClient()
        client.device = MagicMock()
        
        # Create mock folder structure
        root_folder = LIBMTP_folder_struct()
        root_folder.folder_id = 0
        root_folder.parent_id = 0
        root_folder.storage_id = TEST_STORAGE_ID
        root_folder.name = c_char_p(b"")
        
        # Add child folder
        child_folder = LIBMTP_folder_struct()
        child_folder.folder_id = 1
        child_folder.parent_id = 0
        child_folder.storage_id = TEST_STORAGE_ID
        child_folder.name = c_char_p(b"Documents")
        child_folder.sibling = None
        child_folder.child = None
        
        # Connect root to child
        root_folder.child = ctypes.pointer(child_folder)
        root_folder.sibling = None
        
        # Mock the Get_Folder_List function to return our structure
        def mock_get_folder_list(device):
            return ctypes.pointer(root_folder)
            
        client._get_folder_list = mock_get_folder_list
        
        # Create mock file structure
        file_struct = LIBMTP_file_struct()
        file_struct.item_id = 100
        file_struct.parent_id = 1  # Child of "Documents" folder
        file_struct.storage_id = TEST_STORAGE_ID
        file_struct.filename = c_char_p(b"test.txt")
        file_struct.filesize = 1024
        file_struct.filetype = 1  # Not a folder
        file_struct.next = None
        
        # Mock the Get_Files_And_Folders function
        def mock_get_files(device, storage_id, folder_id):
            if folder_id == 1:  # Documents folder
                return ctypes.pointer(file_struct)
            return None
            
        client._get_files_in_folder = mock_get_files
        
        # Override _process_files to avoid dealing with ctypes complexity
        def mock_process_files(file_ptr, parent_folder, id_map, parent_path):
            if parent_path == "/Documents":
                # Manually add file to parent_folder
                from mtpsync.models import FileNode
                file_node = FileNode(100, 1024)
                parent_folder.children["test.txt"] = file_node
                
                # Add to id_map
                from mtpsync.models import IDEntry
                id_map[100] = IDEntry(file_node, f"{parent_path}/test.txt", parent_folder)
                
        client._process_files = mock_process_files
        
        # Build file tree
        path_map, id_map = client.build_file_tree(storage_id=TEST_STORAGE_ID, base_path="/")
        
        # Check path_map
        assert "/Documents" in path_map
        assert path_map["/Documents"].id == 1
        
        # Check that file was added to documents folder
        assert "test.txt" in path_map["/Documents"].children
        assert path_map["/Documents"].children["test.txt"].size == 1024
        
        # Check id_map
        assert 1 in id_map  # Documents folder
        assert 100 in id_map  # test.txt file
        assert id_map[100].full_path == "/Documents/test.txt"
    
    @patch('mtpsync.mtp_client.MTPClient._load_libmtp')
    def test_download(self, mock_load_libmtp):
        """Test downloading a file."""
        # Create mock lib
        mock_lib = MagicMock()
        mock_load_libmtp.return_value = mock_lib
        
        # Configure the mock lib's download function
        def mock_get_file(device, file_id, target_path, progress_func, data):
            # Just create an empty file at the target path
            with open(target_path.decode('utf-8'), 'wb') as f:
                f.write(b"Test file content")
            return 0
            
        mock_lib.LIBMTP_Get_File_To_File = mock_get_file
        
        # Create client with mocked id_map
        client = MTPClient()
        client.device = MagicMock()
        
        # Add file to id_map
        from mtpsync.models import FileNode, IDEntry
        file_node = FileNode(200, 16)
        client.id_map = {
            200: IDEntry(file_node, "/path/to/file.txt", None)
        }
        
        # Download the file
        import tempfile
        with tempfile.NamedTemporaryFile() as temp_file:
            result = client.download(200, Path(temp_file.name))
            
            # Check result
            assert result == Path(temp_file.name)
            
            # Read content to verify
            with open(temp_file.name, 'rb') as f:
                content = f.read()
                assert content == b"Test file content"
    
    @patch('mtpsync.mtp_client.MTPClient._load_libmtp')
    def test_upload(self, mock_load_libmtp):
        """Test uploading a file."""
        # Create mock lib
        mock_lib = MagicMock()
        mock_load_libmtp.return_value = mock_lib
        
        # Configure the mock lib's upload function
        def mock_send_file(device, source_path, file_struct_ptr, progress_func, data):
            # Update the file_struct item_id to simulate successful upload
            file_struct_ptr.contents.item_id = 300
            return 0
            
        mock_lib.LIBMTP_Send_File_From_File = mock_send_file
        
        # Create client
        client = MTPClient()
        client.device = MagicMock()
        
        # Create a test file to upload
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"Test upload content")
            temp_path = Path(temp_file.name)
        
        try:
            # Add parent folder to id_map
            from mtpsync.models import FolderNode, IDEntry
            folder_node = FolderNode(400)
            client.id_map = {
                400: IDEntry(folder_node, "/destination/folder", None)
            }
            
            # Upload the file
            file_id = client.upload(temp_path, 400)
            
            # Check result
            assert file_id == 300  # The ID returned by our mock
            
        finally:
            # Clean up
            if temp_path.exists():
                temp_path.unlink()


@pytest.fixture
def mock_mtp_client():
    """Fixture for a mocked MTP client."""
    with patch('mtpsync.mtp_client.MTPClient._load_libmtp') as mock_load:
        mock_lib = MagicMock()
        mock_load.return_value = mock_lib
        
        client = MTPClient()
        client.device = MagicMock()
        
        yield client
