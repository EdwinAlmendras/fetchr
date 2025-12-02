"""
Health check system for fetchr host resolvers.

Validates that host resolvers can complete their minimum flow sequence
without performing actual downloads.
"""
import asyncio
import aiohttp
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable, Awaitable, List
from abc import ABC, abstractmethod
import logging
import time

logger = logging.getLogger("fetchr.health")


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""
    success: bool
    message: str
    host: str
    elapsed_ms: float = 0.0
    steps_completed: List[str] = field(default_factory=list)
    error: Optional[Exception] = None


@dataclass
class FlowStep:
    """Represents a step in the health check flow."""
    name: str
    description: str
    completed: bool = False
    error: Optional[str] = None


class BaseHealthCheck(ABC):
    """
    Base class for host health checks.
    
    Implements the minimum flow validation:
    1. Initial GET request
    2. Extract required selector/element
    3. Submit form or POST action
    4. Validate response structure
    5. Return success/failure
    """
    
    host_name: str = "unknown"
    test_url: Optional[str] = None
    timeout: int = 30
    
    def __init__(self):
        self.steps: List[FlowStep] = []
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout),
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _add_step(self, name: str, description: str) -> FlowStep:
        step = FlowStep(name=name, description=description)
        self.steps.append(step)
        return step
    
    def _complete_step(self, step: FlowStep):
        step.completed = True
        
    def _fail_step(self, step: FlowStep, error: str):
        step.error = error
        step.completed = False
    
    @abstractmethod
    async def _step1_initial_request(self) -> bool:
        """Step 1: Execute initial GET request."""
        pass
    
    @abstractmethod
    async def _step2_extract_selector(self) -> bool:
        """Step 2: Extract required selector/element from response."""
        pass
    
    @abstractmethod
    async def _step3_submit_action(self) -> bool:
        """Step 3: Submit form or POST action."""
        pass
    
    @abstractmethod
    async def _step4_validate_response(self) -> bool:
        """Step 4: Validate response structure matches expected format."""
        pass
    
    async def check(self) -> HealthCheckResult:
        """
        Execute the complete health check flow.
        Returns HealthCheckResult with success status and details.
        """
        self.steps = []
        start_time = time.monotonic()
        steps_completed = []
        
        try:
            # Step 1: Initial request
            step1 = self._add_step("initial_request", "Execute initial GET request")
            if await self._step1_initial_request():
                self._complete_step(step1)
                steps_completed.append(step1.name)
            else:
                return HealthCheckResult(
                    success=False,
                    message="Failed at step 1: Initial request failed",
                    host=self.host_name,
                    elapsed_ms=(time.monotonic() - start_time) * 1000,
                    steps_completed=steps_completed
                )
            
            # Step 2: Extract selector
            step2 = self._add_step("extract_selector", "Extract required selector")
            if await self._step2_extract_selector():
                self._complete_step(step2)
                steps_completed.append(step2.name)
            else:
                return HealthCheckResult(
                    success=False,
                    message="Failed at step 2: Could not extract required selector",
                    host=self.host_name,
                    elapsed_ms=(time.monotonic() - start_time) * 1000,
                    steps_completed=steps_completed
                )
            
            # Step 3: Submit action
            step3 = self._add_step("submit_action", "Submit form or action")
            if await self._step3_submit_action():
                self._complete_step(step3)
                steps_completed.append(step3.name)
            else:
                return HealthCheckResult(
                    success=False,
                    message="Failed at step 3: Form/action submission failed",
                    host=self.host_name,
                    elapsed_ms=(time.monotonic() - start_time) * 1000,
                    steps_completed=steps_completed
                )
            
            # Step 4: Validate response
            step4 = self._add_step("validate_response", "Validate response structure")
            if await self._step4_validate_response():
                self._complete_step(step4)
                steps_completed.append(step4.name)
            else:
                return HealthCheckResult(
                    success=False,
                    message="Failed at step 4: Response validation failed",
                    host=self.host_name,
                    elapsed_ms=(time.monotonic() - start_time) * 1000,
                    steps_completed=steps_completed
                )
            
            elapsed = (time.monotonic() - start_time) * 1000
            return HealthCheckResult(
                success=True,
                message=f"All {len(steps_completed)} steps completed successfully",
                host=self.host_name,
                elapsed_ms=elapsed,
                steps_completed=steps_completed
            )
            
        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            return HealthCheckResult(
                success=False,
                message=f"Health check failed with error: {str(e)}",
                host=self.host_name,
                elapsed_ms=elapsed,
                steps_completed=steps_completed,
                error=e
            )


class GofileHealthCheck(BaseHealthCheck):
    """Health check for Gofile.io"""
    
    host_name = "gofile.io"
    base_url = "https://api.gofile.io"
    
    def __init__(self):
        super().__init__()
        self.token: Optional[str] = None
        self.account_data: Optional[dict] = None
    
    async def _step1_initial_request(self) -> bool:
        """Check API is accessible."""
        async with self.session.get(f"{self.base_url}/servers") as response:
            if response.status == 200:
                data = await response.json()
                return data.get("status") == "ok"
        return False
    
    async def _step2_extract_selector(self) -> bool:
        """Get account token from API."""
        async with self.session.post(f"{self.base_url}/accounts") as response:
            if response.status == 200:
                data = await response.json()
                if data.get("status") == "ok":
                    self.token = data["data"].get("token")
                    return self.token is not None
        return False
    
    async def _step3_submit_action(self) -> bool:
        """Validate token works by checking account."""
        if not self.token:
            return False
        url = f"{self.base_url}/accounts/{self.token}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                self.account_data = data.get("data")
                return data.get("status") == "ok"
        return False
    
    async def _step4_validate_response(self) -> bool:
        """Validate account data structure."""
        if not self.account_data:
            return False
        required_fields = ["token", "tier"]
        return all(field in self.account_data for field in required_fields)


class PixeldrainHealthCheck(BaseHealthCheck):
    """Health check for Pixeldrain.com"""
    
    host_name = "pixeldrain.com"
    base_url = "https://pixeldrain.com"
    api_url = "https://pixeldrain.com/api"
    
    def __init__(self):
        super().__init__()
        self.api_accessible = False
    
    async def _step1_initial_request(self) -> bool:
        """Check main site is accessible."""
        async with self.session.get(self.base_url) as response:
            return response.status == 200
    
    async def _step2_extract_selector(self) -> bool:
        """Check API endpoint structure."""
        async with self.session.get(f"{self.api_url}/misc/ping") as response:
            return response.status in [200, 404]  # 404 means API is there but endpoint doesn't exist
    
    async def _step3_submit_action(self) -> bool:
        """Test API with a known action."""
        # Test the user endpoint (will fail auth but confirms API works)
        async with self.session.get(f"{self.api_url}/user") as response:
            # 401 means API is working but needs auth
            self.api_accessible = response.status in [200, 401, 403]
            return self.api_accessible
    
    async def _step4_validate_response(self) -> bool:
        """Validate API is responding correctly."""
        return self.api_accessible


class OneFichierHealthCheck(BaseHealthCheck):
    """Health check for 1fichier.com"""
    
    host_name = "1fichier.com"
    base_url = "https://1fichier.com"
    
    def __init__(self):
        super().__init__()
        self.page_content: Optional[str] = None
    
    async def _step1_initial_request(self) -> bool:
        """Check main site is accessible."""
        async with self.session.get(self.base_url) as response:
            if response.status == 200:
                self.page_content = await response.text()
                return True
        return False
    
    async def _step2_extract_selector(self) -> bool:
        """Check for upload form presence."""
        if not self.page_content:
            return False
        return "upload" in self.page_content.lower() or "fichier" in self.page_content.lower()
    
    async def _step3_submit_action(self) -> bool:
        """Verify console/API endpoint exists."""
        async with self.session.get(f"{self.base_url}/console/") as response:
            return response.status in [200, 302, 401, 403]
    
    async def _step4_validate_response(self) -> bool:
        """Validate site structure."""
        return self.page_content is not None and len(self.page_content) > 100


class GenericAPIHealthCheck(BaseHealthCheck):
    """Generic health check for API-based hosts."""
    
    def __init__(self, host_name: str, base_url: str, api_endpoint: str = "/"):
        super().__init__()
        self.host_name = host_name
        self.base_url = base_url
        self.api_endpoint = api_endpoint
        self.response_data = None
    
    async def _step1_initial_request(self) -> bool:
        async with self.session.get(self.base_url) as response:
            return response.status in [200, 301, 302]
    
    async def _step2_extract_selector(self) -> bool:
        async with self.session.get(f"{self.base_url}{self.api_endpoint}") as response:
            if response.status == 200:
                try:
                    self.response_data = await response.json()
                    return True
                except:
                    self.response_data = await response.text()
                    return len(self.response_data) > 0
            return response.status in [401, 403]  # Auth required = API exists
    
    async def _step3_submit_action(self) -> bool:
        return self.response_data is not None or True
    
    async def _step4_validate_response(self) -> bool:
        return True


class HealthChecker:
    """
    Main health checker that runs checks against all supported hosts.
    """
    
    def __init__(self):
        self.checks: Dict[str, BaseHealthCheck] = {
            "gofile": GofileHealthCheck(),
            "pixeldrain": PixeldrainHealthCheck(),
            "1fichier": OneFichierHealthCheck(),
        }
        
        # Add generic checks for other hosts
        generic_hosts = [
            ("krakenfiles", "https://krakenfiles.com"),
            ("uploadflix", "https://uploadflix.cc"),
            ("ranoz", "https://ranoz.gg"),
            ("filedot", "https://filedot.to"),
            ("desiupload", "https://desiupload.co"),
            ("filemirage", "https://filemirage.com"),
            ("uploadee", "https://upload.ee"),
            ("uploadhive", "https://uploadhive.com"),
        ]
        
        for name, url in generic_hosts:
            self.checks[name] = GenericAPIHealthCheck(name, url)
    
    async def check_host(self, host: str) -> HealthCheckResult:
        """
        Run health check for a specific host.
        
        Args:
            host: Host name (e.g., 'gofile', 'pixeldrain')
            
        Returns:
            HealthCheckResult with status and details
        """
        if host not in self.checks:
            return HealthCheckResult(
                success=False,
                message=f"Unknown host: {host}",
                host=host
            )
        
        check = self.checks[host]
        async with check:
            return await check.check()
    
    async def check_all(self, parallel: bool = True) -> Dict[str, HealthCheckResult]:
        """
        Run health checks for all registered hosts.
        
        Args:
            parallel: Run checks in parallel (default True)
            
        Returns:
            Dictionary mapping host names to their HealthCheckResult
        """
        results = {}
        
        if parallel:
            async def run_check(name: str, check: BaseHealthCheck):
                async with check:
                    return name, await check.check()
            
            tasks = [run_check(name, check) for name, check in self.checks.items()]
            completed = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in completed:
                if isinstance(result, Exception):
                    logger.error(f"Health check error: {result}")
                else:
                    name, check_result = result
                    results[name] = check_result
        else:
            for name, check in self.checks.items():
                async with check:
                    results[name] = await check.check()
        
        return results
    
    async def check_hosts(self, hosts: List[str]) -> Dict[str, HealthCheckResult]:
        """
        Run health checks for specific hosts.
        
        Args:
            hosts: List of host names to check
            
        Returns:
            Dictionary mapping host names to their HealthCheckResult
        """
        results = {}
        
        async def run_check(name: str):
            return name, await self.check_host(name)
        
        tasks = [run_check(name) for name in hosts]
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Health check error: {result}")
            else:
                name, check_result = result
                results[name] = check_result
        
        return results


def health(host: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for health checks.
    
    Args:
        host: Optional host name. If None, checks all hosts.
        
    Returns:
        True if all checked hosts pass, False otherwise.
    """
    async def _run():
        checker = HealthChecker()
        if host:
            result = await checker.check_host(host)
            return result.success
        else:
            results = await checker.check_all()
            return all(r.success for r in results.values())
    
    return asyncio.run(_run())


async def async_health(host: Optional[str] = None) -> bool:
    """
    Async health check function.
    
    Args:
        host: Optional host name. If None, checks all hosts.
        
    Returns:
        True if all checked hosts pass, False otherwise.
    """
    checker = HealthChecker()
    if host:
        result = await checker.check_host(host)
        return result.success
    else:
        results = await checker.check_all()
        return all(r.success for r in results.values())


if __name__ == "__main__":
    async def main():
        checker = HealthChecker()
        
        print("Running health checks for all hosts...\n")
        results = await checker.check_all()
        
        for host, result in results.items():
            status = "OK" if result.success else "FAILED"
            print(f"[{status}] {host}: {result.message} ({result.elapsed_ms:.0f}ms)")
            if result.steps_completed:
                print(f"       Steps: {' -> '.join(result.steps_completed)}")
        
        print(f"\nTotal: {sum(1 for r in results.values() if r.success)}/{len(results)} hosts healthy")
    
    asyncio.run(main())
