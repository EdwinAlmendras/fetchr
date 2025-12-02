"""
Tests for the main Downloader class.
"""
import pytest
from pathlib import Path
from fetchr import Downloader, SUPPORTED_HOSTS


class TestDownloader:
    """Tests for Downloader class."""
    
    def test_create_downloader(self):
        """Test creating Downloader instance."""
        downloader = Downloader()
        assert downloader is not None
        assert downloader.max_concurrent_global == 20
    
    def test_create_downloader_custom_concurrent(self):
        """Test creating Downloader with custom concurrency."""
        downloader = Downloader(max_concurrent_global=5)
        assert downloader.max_concurrent_global == 5
    
    def test_supported_hosts_list(self):
        """Test SUPPORTED_HOSTS is populated."""
        assert len(SUPPORTED_HOSTS) > 0
        assert "pixeldrain.com" in SUPPORTED_HOSTS
        assert "gofile.io" in SUPPORTED_HOSTS
    
    def test_get_host_from_url(self):
        """Test host extraction from URL."""
        downloader = Downloader()
        
        assert downloader._get_host("https://pixeldrain.com/u/abc") == "pixeldrain.com"
        assert downloader._get_host("https://www.gofile.io/d/xyz") == "gofile.io"
        assert downloader._get_host("https://1fichier.com/?abc") == "1fichier.com"
    
    def test_get_host_strips_www(self):
        """Test that www prefix is stripped from host."""
        downloader = Downloader()
        
        assert downloader._get_host("https://www.example.com/file") == "example.com"
    
    def test_downloader_has_parallel_downloader(self):
        """Test Downloader has parallel downloader component."""
        downloader = Downloader()
        assert downloader.parallel_downloader is not None
    
    def test_downloader_has_aria2c_downloader(self):
        """Test Downloader has aria2c downloader component."""
        downloader = Downloader()
        assert downloader.aria2c_downloader is not None
    
    def test_downloader_semaphores_created(self):
        """Test that host semaphores are created."""
        downloader = Downloader()
        assert len(downloader.semaphores) > 0


class TestDownloaderCheckExists:
    """Tests for file existence checking."""
    
    def test_check_exists_no_file(self, tmp_path):
        """Test check_exists returns False when file doesn't exist."""
        downloader = Downloader()
        from fetchr.types import DownloadInfo
        
        info = DownloadInfo(
            download_url="https://example.com/file.zip",
            filename="nonexistent.zip",
            size=1024
        )
        
        result = downloader.check_exists(tmp_path, info)
        assert result is None or result is False
    
    def test_check_exists_file_exists_same_size(self, tmp_path):
        """Test check_exists returns True when file exists with same size."""
        downloader = Downloader()
        from fetchr.types import DownloadInfo
        
        # Create a test file
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"x" * 1024)
        
        info = DownloadInfo(
            download_url="https://example.com/test.zip",
            filename="test.zip",
            size=1024
        )
        
        result = downloader.check_exists(tmp_path, info)
        assert result is True
    
    def test_check_exists_file_exists_different_size(self, tmp_path):
        """Test check_exists returns False when file exists with different size."""
        downloader = Downloader()
        from fetchr.types import DownloadInfo
        
        # Create a test file with different size
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b"x" * 512)
        
        info = DownloadInfo(
            download_url="https://example.com/test.zip",
            filename="test.zip",
            size=1024
        )
        
        result = downloader.check_exists(tmp_path, info)
        assert result is False
