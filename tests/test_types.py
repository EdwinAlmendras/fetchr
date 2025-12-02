"""
Tests for fetchr types module.
"""
import pytest
from fetchr.types import DownloadInfo, FileDeletedError


class TestDownloadInfo:
    """Tests for DownloadInfo dataclass."""
    
    def test_create_download_info(self):
        """Test creating DownloadInfo instance."""
        info = DownloadInfo(
            download_url="https://example.com/file.zip",
            filename="file.zip",
            size=1024,
            headers={"Authorization": "Bearer token"}
        )
        
        assert info.download_url == "https://example.com/file.zip"
        assert info.filename == "file.zip"
        assert info.size == 1024
        assert info.headers["Authorization"] == "Bearer token"
    
    def test_download_info_default_headers(self):
        """Test DownloadInfo with default headers."""
        info = DownloadInfo(
            download_url="https://example.com/file.zip",
            filename="file.zip",
            size=1024
        )
        
        assert info.headers == {}
    
    def test_download_info_zero_size(self):
        """Test DownloadInfo with zero size."""
        info = DownloadInfo(
            download_url="https://example.com/file.zip",
            filename="file.zip",
            size=0
        )
        
        assert info.size == 0


class TestFileDeletedError:
    """Tests for FileDeletedError exception."""
    
    def test_file_deleted_error(self):
        """Test FileDeletedError can be raised."""
        with pytest.raises(FileDeletedError):
            raise FileDeletedError("File was deleted")
    
    def test_file_deleted_error_message(self):
        """Test FileDeletedError message."""
        try:
            raise FileDeletedError("File not found on server")
        except FileDeletedError as e:
            assert "File not found" in str(e)
