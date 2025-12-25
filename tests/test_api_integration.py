"""
Integration tests for Fetchr API.
Tests all API routes with real HTTP requests against live server.

Prerequisites:
  1. Run aria2c: aria2c --enable-rpc --rpc-listen-port=6800 --rpc-allow-origin-all
  2. Run API: uvicorn api.main:app --host 127.0.0.1 --port 6565
  3. Run tests: pytest tests/test_api_integration.py -v
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
        except Exception as e:
            pytest.skip(f"API server not running: {e}")
        yield c


# ============== Health Tests ==============

class TestHealth:
    async def test_root(self, client):
        r = await client.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == "Fetchr API"

    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200


# ============== Package Tests ==============

class TestPackages:
    async def test_list_packages(self, client):
        r = await client.get("/api/packages/")
        assert r.status_code == 200

    async def test_create_package(self, client):
        r = await client.post("/api/packages/", json={"name": "Test Package"})
        assert r.status_code == 201
        assert r.json()["name"] == "Test Package"

    async def test_get_package(self, client):
        # Create
        create = await client.post("/api/packages/", json={"name": "Get Test"})
        pkg_id = create.json()["id"]
        # Get
        r = await client.get(f"/api/packages/{pkg_id}")
        assert r.status_code == 200
        assert r.json()["id"] == pkg_id

    async def test_get_package_not_found(self, client):
        r = await client.get("/api/packages/99999")
        assert r.status_code == 404

    async def test_update_package(self, client):
        create = await client.post("/api/packages/", json={"name": "Update Test"})
        pkg_id = create.json()["id"]
        r = await client.put(f"/api/packages/{pkg_id}", json={"name": "Updated"})
        assert r.status_code == 200
        assert r.json()["name"] == "Updated"

    async def test_get_package_stats(self, client):
        create = await client.post("/api/packages/", json={"name": "Stats Test"})
        pkg_id = create.json()["id"]
        r = await client.get(f"/api/packages/{pkg_id}/stats")
        assert r.status_code == 200
        assert "total_files" in r.json()

    async def test_delete_package(self, client):
        create = await client.post("/api/packages/", json={"name": "Delete Test"})
        pkg_id = create.json()["id"]
        r = await client.delete(f"/api/packages/{pkg_id}")
        assert r.status_code == 204


# ============== Download List Tests ==============

class TestDownloadsList:
    async def test_list_downloads(self, client):
        r = await client.get("/api/downloads/")
        assert r.status_code == 200

    async def test_list_active(self, client):
        r = await client.get("/api/downloads/active")
        assert r.status_code == 200

    async def test_list_queued(self, client):
        r = await client.get("/api/downloads/queued")
        assert r.status_code == 200

    async def test_list_completed(self, client):
        r = await client.get("/api/downloads/completed")
        assert r.status_code == 200

    async def test_list_errors(self, client):
        r = await client.get("/api/downloads/errors")
        assert r.status_code == 200


# ============== Download Add Tests (/add/{package_id}) ==============

class TestDownloadsAdd:
    async def test_add_download(self, client):
        # Create package
        pkg = await client.post("/api/packages/", json={"name": "Add Test"})
        pkg_id = pkg.json()["id"]
        # Add download using /add/{package_id}
        r = await client.post(
            f"/api/downloads/add/{pkg_id}",
            json={"url": TEST_DOWNLOAD_URL, "filename": "test.bin", "resolve": False}
        )
        assert r.status_code == 201
        assert r.json()["filename"] == "test.bin"

    async def test_add_bulk_downloads(self, client):
        r = await client.post(
            "/api/downloads/bulk",
            json={"package_name": "Bulk Test", "urls": [TEST_DOWNLOAD_URL], "resolve": False}
        )
        assert r.status_code == 201
        assert isinstance(r.json(), list)

    async def test_add_to_invalid_package(self, client):
        r = await client.post(
            "/api/downloads/add/99999",
            json={"url": TEST_DOWNLOAD_URL, "resolve": False}
        )
        assert r.status_code == 404


# ============== Download File Tests (/file/{file_id}) ==============

class TestDownloadsFile:
    async def _create_download(self, client):
        """Helper to create a package and download."""
        pkg = await client.post("/api/packages/", json={"name": "File Test"})
        pkg_id = pkg.json()["id"]
        dl = await client.post(
            f"/api/downloads/add/{pkg_id}",
            json={"url": TEST_DOWNLOAD_URL, "resolve": False}
        )
        return dl.json()["id"]

    async def test_get_download(self, client):
        file_id = await self._create_download(client)
        r = await client.get(f"/api/downloads/file/{file_id}")
        assert r.status_code == 200
        assert r.json()["id"] == file_id

    async def test_get_download_not_found(self, client):
        r = await client.get("/api/downloads/file/99999")
        assert r.status_code == 404

    async def test_get_download_details(self, client):
        file_id = await self._create_download(client)
        r = await client.get(f"/api/downloads/file/{file_id}/details")
        assert r.status_code == 200
        assert "download_speed" in r.json()

    async def test_update_download(self, client):
        file_id = await self._create_download(client)
        r = await client.put(
            f"/api/downloads/file/{file_id}",
            json={"filename": "renamed.bin"}
        )
        assert r.status_code == 200
        assert r.json()["filename"] == "renamed.bin"

    async def test_pause_download(self, client):
        file_id = await self._create_download(client)
        r = await client.post(f"/api/downloads/file/{file_id}/pause")
        assert r.status_code in [200, 404]  # May fail if already paused

    async def test_resume_download(self, client):
        file_id = await self._create_download(client)
        await client.post(f"/api/downloads/file/{file_id}/pause")
        r = await client.post(f"/api/downloads/file/{file_id}/resume")
        assert r.status_code in [200, 404]

    async def test_patch_status(self, client):
        file_id = await self._create_download(client)
        r = await client.patch(
            f"/api/downloads/file/{file_id}",
            json={"action": "pause"}
        )
        assert r.status_code in [200, 404]

    async def test_delete_download(self, client):
        file_id = await self._create_download(client)
        r = await client.delete(f"/api/downloads/file/{file_id}")
        assert r.status_code == 204
        # Verify deleted
        r2 = await client.get(f"/api/downloads/file/{file_id}")
        assert r2.status_code == 404

    async def test_move_download(self, client):
        # Create two packages
        pkg1 = await client.post("/api/packages/", json={"name": "Source"})
        pkg2 = await client.post("/api/packages/", json={"name": "Target"})
        pkg1_id = pkg1.json()["id"]
        pkg2_id = pkg2.json()["id"]
        # Create download in pkg1
        dl = await client.post(
            f"/api/downloads/add/{pkg1_id}",
            json={"url": TEST_DOWNLOAD_URL, "resolve": False}
        )
        file_id = dl.json()["id"]
        # Move to pkg2
        r = await client.post(
            f"/api/downloads/file/{file_id}/move",
            json={"target_package_id": pkg2_id}
        )
        assert r.status_code == 200
        assert r.json()["package_id"] == pkg2_id


# ============== Bulk Actions Tests ==============

class TestBulkActions:
    async def test_pause_all(self, client):
        r = await client.post("/api/downloads/pause-all")
        assert r.status_code == 200
        assert "paused" in r.json()

    async def test_resume_all(self, client):
        r = await client.post("/api/downloads/resume-all")
        assert r.status_code == 200
        assert "resumed" in r.json()

    async def test_clear_completed(self, client):
        r = await client.delete("/api/downloads/clear/completed")
        assert r.status_code == 200
        assert "cleared" in r.json()

    async def test_clear_errors(self, client):
        r = await client.delete("/api/downloads/clear/errors")
        assert r.status_code == 200


# ============== Stats Tests ==============

class TestStats:
    async def test_stats_summary(self, client):
        r = await client.get("/api/downloads/stats/summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_packages" in data
        assert "total_files" in data

    async def test_stats_speed(self, client):
        r = await client.get("/api/downloads/stats/speed")
        assert r.status_code == 200
        assert "download_speed" in r.json()


# ============== Logs Tests ==============

class TestLogs:
    async def test_list_logs(self, client):
        r = await client.get("/api/logs/")
        assert r.status_code == 200

    async def test_get_log(self, client):
        r = await client.get("/api/logs/fetchr.log?tail=10")
        assert r.status_code == 200


# ============== Package Actions Tests ==============

class TestPackageActions:
    async def test_pause_package(self, client):
        pkg = await client.post("/api/packages/", json={"name": "Pause Pkg Test"})
        pkg_id = pkg.json()["id"]
        r = await client.post(f"/api/packages/{pkg_id}/pause-all")
        assert r.status_code == 200

    async def test_resume_package(self, client):
        pkg = await client.post("/api/packages/", json={"name": "Resume Pkg Test"})
        pkg_id = pkg.json()["id"]
        r = await client.post(f"/api/packages/{pkg_id}/resume-all")
        assert r.status_code == 200


# ============== Cleanup ==============

class TestCleanup:
    async def test_delete_all_requires_confirm(self, client):
        r = await client.delete("/api/packages/")
        assert r.status_code == 400

    async def test_delete_all_with_confirm(self, client):
        r = await client.delete("/api/packages/?confirm=true")
        assert r.status_code == 200
