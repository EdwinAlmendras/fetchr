"""
Tests for the health check system.

These tests validate that the health check flow sequence
works correctly for each supported host.
"""
import pytest
from fetchr.health import (
    HealthChecker,
    HealthCheckResult,
    GofileHealthCheck,
    PixeldrainHealthCheck,
    OneFichierHealthCheck,
    health,
    async_health,
)


class TestHealthCheckResult:
    """Tests for HealthCheckResult dataclass."""
    
    def test_successful_result(self):
        result = HealthCheckResult(
            success=True,
            message="All steps completed",
            host="test_host",
            elapsed_ms=100.0,
            steps_completed=["step1", "step2"]
        )
        assert result.success is True
        assert result.host == "test_host"
        assert len(result.steps_completed) == 2
    
    def test_failed_result(self):
        result = HealthCheckResult(
            success=False,
            message="Step 2 failed",
            host="test_host",
            elapsed_ms=50.0,
            steps_completed=["step1"],
            error=Exception("Test error")
        )
        assert result.success is False
        assert result.error is not None


class TestGofileHealthCheck:
    """Tests for Gofile health check."""
    
    async def test_gofile_check_structure(self):
        """Test that Gofile health check has correct structure."""
        check = GofileHealthCheck()
        assert check.host_name == "gofile.io"
        assert check.base_url == "https://api.gofile.io"
    
    async def test_gofile_health_check_flow(self):
        """Test Gofile health check completes the flow."""
        check = GofileHealthCheck()
        async with check:
            result = await check.check()
        
        assert isinstance(result, HealthCheckResult)
        assert result.host == "gofile.io"
        assert result.elapsed_ms > 0
        # Note: Success depends on actual API availability


class TestPixeldrainHealthCheck:
    """Tests for Pixeldrain health check."""
    
    async def test_pixeldrain_check_structure(self):
        """Test that Pixeldrain health check has correct structure."""
        check = PixeldrainHealthCheck()
        assert check.host_name == "pixeldrain.com"
        assert "pixeldrain.com" in check.base_url
    
    async def test_pixeldrain_health_check_flow(self):
        """Test Pixeldrain health check completes the flow."""
        check = PixeldrainHealthCheck()
        async with check:
            result = await check.check()
        
        assert isinstance(result, HealthCheckResult)
        assert result.host == "pixeldrain.com"


class TestOneFichierHealthCheck:
    """Tests for 1fichier health check."""
    
    async def test_1fichier_check_structure(self):
        """Test that 1fichier health check has correct structure."""
        check = OneFichierHealthCheck()
        assert check.host_name == "1fichier.com"
    
    async def test_1fichier_health_check_flow(self):
        """Test 1fichier health check completes the flow."""
        check = OneFichierHealthCheck()
        async with check:
            result = await check.check()
        
        assert isinstance(result, HealthCheckResult)
        assert result.host == "1fichier.com"


class TestHealthChecker:
    """Tests for the main HealthChecker class."""
    
    async def test_checker_has_registered_hosts(self):
        """Test that checker has hosts registered."""
        checker = HealthChecker()
        assert len(checker.checks) > 0
        assert "gofile" in checker.checks
        assert "pixeldrain" in checker.checks
    
    async def test_check_unknown_host(self):
        """Test checking an unknown host returns failure."""
        checker = HealthChecker()
        result = await checker.check_host("unknown_host_xyz")
        
        assert result.success is False
        assert "Unknown host" in result.message
    
    async def test_check_single_host(self):
        """Test checking a single host."""
        checker = HealthChecker()
        result = await checker.check_host("gofile")
        
        assert isinstance(result, HealthCheckResult)
        assert result.host == "gofile.io"
    
    async def test_check_all_hosts(self):
        """Test checking all hosts."""
        checker = HealthChecker()
        results = await checker.check_all()
        
        assert isinstance(results, dict)
        assert len(results) > 0
        for host, result in results.items():
            assert isinstance(result, HealthCheckResult)
    
    async def test_check_specific_hosts(self):
        """Test checking specific hosts."""
        checker = HealthChecker()
        results = await checker.check_hosts(["gofile", "pixeldrain"])
        
        assert len(results) == 2
        assert "gofile" in results
        assert "pixeldrain" in results


class TestHealthFunctions:
    """Tests for the convenience health functions."""
    
    async def test_async_health_single(self):
        """Test async health check for single host."""
        result = await async_health("gofile")
        assert isinstance(result, bool)
    
    async def test_async_health_all(self):
        """Test async health check for all hosts."""
        result = await async_health()
        assert isinstance(result, bool)


class TestHealthCheckSteps:
    """Tests for individual health check steps."""
    
    async def test_steps_are_recorded(self):
        """Test that completed steps are recorded."""
        check = GofileHealthCheck()
        async with check:
            result = await check.check()
        
        # Steps should be recorded regardless of success
        assert isinstance(result.steps_completed, list)
    
    async def test_elapsed_time_recorded(self):
        """Test that elapsed time is recorded."""
        check = PixeldrainHealthCheck()
        async with check:
            result = await check.check()
        
        assert result.elapsed_ms >= 0


class TestIntegrationHealthChecks:
    """
    Integration tests that verify actual host connectivity.
    These tests may fail if hosts are down or network is unavailable.
    """
    
    @pytest.mark.slow
    async def test_all_hosts_reachable(self):
        """Test that all configured hosts are reachable."""
        checker = HealthChecker()
        results = await checker.check_all()
        
        reachable_count = sum(1 for r in results.values() if r.success)
        total_count = len(results)
        
        print(f"\n{reachable_count}/{total_count} hosts are healthy")
        for host, result in results.items():
            status = "OK" if result.success else "FAILED"
            print(f"  [{status}] {host}: {result.message}")
        
        # At least some hosts should be reachable
        assert reachable_count > 0, "No hosts are reachable"
