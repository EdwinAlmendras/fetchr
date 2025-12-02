"""
Pytest configuration and fixtures for fetchr tests.
"""
import pytest


@pytest.fixture
def sample_urls():
    """Sample URLs for testing (these may not be valid real files)."""
    return {
        "pixeldrain": "https://pixeldrain.com/u/abc123",
        "gofile": "https://gofile.io/d/abc123",
        "1fichier": "https://1fichier.com/?abc123",
    }
