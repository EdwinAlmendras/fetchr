"""
Integration tests for Link Grabber API.
"""
import pytest
import asyncio
from httpx import AsyncClient

TEST_BASE_URL = "http://127.0.0.1:6565"
TEST_DOWNLOAD_URL = "https://speed.hetzner.de/1KB.bin"

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="module")
async def client():
    async with AsyncClient(base_url=TEST_BASE_URL, timeout=30.0) as c:
        try:
            r = await c.get("/")
            if r.status_code != 200:
                pytest.skip("API server not responding")
        except:
            pytest.skip("API server not running")
        yield c

class TestGrabber:
    async def test_analyze_links(self, client):
        """Test analyzing links creates a GRABBER package with QUEUED files."""
        response = await client.post(
            "/api/grabber/analyze",
            json={
                "package_name": "Grabber Test Package",
                "urls": [TEST_DOWNLOAD_URL]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Grabber Test Package"
        assert data["status"] == "GRABBER"  # Package should be GRABBER
        assert len(data["files"]) >= 1
        # Files should be QUEUED (success) or ERROR (failure)
        for f in data["files"]:
            assert f["status"] in ["QUEUED", "ERROR"]
        return data["id"]

    async def test_list_grabber_packages(self, client):
        """Test listing packages with GRABBER status."""
        # Ensure at least one exists
        await self.test_analyze_links(client)
        
        response = await client.get("/api/grabber/packages")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        # All packages should have status GRABBER
        for pkg in data:
            assert pkg["status"] == "GRABBER"

    async def test_start_package(self, client):
        """Test starting a package changes status to ACTIVE."""
        # Create package first
        pkg_id = await self.test_analyze_links(client)
        
        # Start it
        response = await client.post(
            "/api/grabber/start-package",
            json={"package_id": pkg_id}
        )
        assert response.status_code == 200
        
        # Verify package is no longer in grabber list
        list_response = await client.get("/api/grabber/packages")
        pkg_ids = [p["id"] for p in list_response.json()]
        assert pkg_id not in pkg_ids  # Should be ACTIVE now, not GRABBER
