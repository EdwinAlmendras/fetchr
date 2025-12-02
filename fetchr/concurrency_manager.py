"""
Concurrency Manager for controlling download limits per host
"""
import asyncio
from collections import defaultdict
from urllib.parse import urlparse
from typing import Dict, Optional, List, Any
from pathlib import Path
from rich.console import Console
from fetchr.main import Downloader
console = Console()

class ConcurrencyManager:
    """Manages download concurrency limits per host"""
    
    def __init__(self, host_limits: Optional[Dict[str, int]] = None):
        """
        Initialize concurrency manager with host limits
        
        Args:
            host_limits: Dictionary with host -> max_concurrent_downloads
        """
        # Default limits per host
        default_limits = {
            "pixeldrain.com": 10,      # More tolerant
            "gofile.io": 5,            # Moderate limit
            "anonfile.de": 20,          # More restrictive
            "filedot.to": 5,           # Moderate
            "desiupload.co": 2,        # Restrictive
            "axfc.net": 20,            # Very restrictive
            "filemirage.com": 5,       # Restrictive
            "uploadhive.com": 5,       # Very restrictive
            "default": 1               # Conservative default
        }
        
        # Merge with custom limits
        self.host_limits = {**default_limits, **(host_limits or {})}
        
        # Create semaphores for each host
        self.host_semaphores = {
            host: asyncio.Semaphore(limit) 
            for host, limit in self.host_limits.items()
        }
        
        # Track active downloads per host
        self.active_downloads = defaultdict(int)
        
        # Statistics
        self.total_downloads = 0
        self.successful_downloads = 0
        self.failed_downloads = 0
    
    def get_semaphore(self, host: str) -> asyncio.Semaphore:
        """Get the appropriate semaphore for a host"""
        # Clean host name
        if host.startswith('www.'):
            host = host[4:]
        
        # Find matching semaphore
        for host_key, semaphore in self.host_semaphores.items():
            if host_key in host or host in host_key:
                return semaphore
        
        # Return default if no match found
        return self.host_semaphores["default"]
    
    def get_host_from_url(self, url: str) -> str:
        """Extract host from URL"""
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        if host.startswith('www.'):
            host = host[4:]
        return host
    
    async def download_with_limit(self, downloader: Downloader, url: str, download_dir: Path, 
                                callback_progress=None, solve_captcha=None) -> Any:
        """
        Download a file respecting host concurrency limits
        
        Args:
            downloader: Downloader instance
            url: URL to download
            download_dir: Directory to save file
            callback_progress: Progress callback function
            solve_captcha: Captcha solving function
            
        Returns:
            Download result
        """
        host = self.get_host_from_url(url)
        semaphore = self.get_semaphore(host)
        
        async with semaphore:
            self.active_downloads[host] += 1
            self.total_downloads += 1
            
            try:
                result = await downloader.download_file(
                    url, download_dir, callback_progress, solve_captcha
                )
                self.successful_downloads += 1
                return result
                
            except Exception as e:
                self.failed_downloads += 1
                raise e
                
            finally:
                self.active_downloads[host] -= 1
    
    async def download_multiple_files(self, downloader, urls: List[str], download_dir: Path,
                                    callback_progress=None, solve_captcha=None) -> List[Any]:
        """
        Download multiple files respecting concurrency limits
        
        Args:
            downloader: Downloader instance
            urls: List of URLs to download
            download_dir: Directory to save files
            callback_progress: Progress callback function
            solve_captcha: Captcha solving function
            
        Returns:
            List of successful download results
        """
        if not urls:
            return []
        
        console.print(f"📥 Iniciando descarga de {len(urls)} archivos")
        
        # Create download tasks
        tasks = []
        for url in urls:
            task = asyncio.create_task(
                self.download_with_limit(
                    downloader, url, download_dir, callback_progress, solve_captcha
                )
            )
            tasks.append(task)
        
        # Execute all downloads
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful downloads
        successful_downloads = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                console.print(f"❌ Error descargando {urls[i]}: {result}")
            else:
                successful_downloads.append(result)
        
        console.print(f"📊 Descargas completadas: {len(successful_downloads)}/{len(urls)}")
        return successful_downloads
    
    def get_stats(self) -> Dict[str, Any]:
        """Get download statistics"""
        return {
            "total_downloads": self.total_downloads,
            "successful_downloads": self.successful_downloads,
            "failed_downloads": self.failed_downloads,
            "success_rate": (self.successful_downloads / max(self.total_downloads, 1)) * 100,
            "active_downloads": dict(self.active_downloads),
            "host_limits": self.host_limits
        }
    
    def print_stats(self):
        """Print current statistics"""
        stats = self.get_stats()
        
        console.print("\n📊 [bold]Estadísticas de Descarga[/bold]")
        console.print(f"Total descargas: {stats['total_downloads']}")
        console.print(f"Exitosas: {stats['successful_downloads']}")
        console.print(f"Fallidas: {stats['failed_downloads']}")
        console.print(f"Tasa de éxito: {stats['success_rate']:.1f}%")
        
        if stats['active_downloads']:
            for host, count in stats['active_downloads'].items():
                if count > 0:
                    console.print(f"  {host}: {count}")
    
    def update_host_limit(self, host: str, new_limit: int):
        """Update concurrency limit for a specific host"""
        self.host_limits[host] = new_limit
        self.host_semaphores[host] = asyncio.Semaphore(new_limit)
        console.print(f"🔧 Límite actualizado para {host}: {new_limit}")
    
    async def monitor_downloads(self, interval: float = 5.0):
        """Monitor active downloads (for debugging)"""
        while True:
            active_count = sum(self.active_downloads.values())
            if active_count > 0:
                for host, count in self.active_downloads.items():
                    if count > 0:
                        console.print(f"  {host}: {count}")
            await asyncio.sleep(interval)
