import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
import logging
from fetchr.network import get_random_proxy
from fetchr.config import DEBRID_GATEWAY

logger = logging.getLogger(__name__)


class UsersDriveResolver(AbstractHostResolver):
    
    def __init__(self):
        proxy = get_random_proxy()
        self.proxy = proxy
        self.session = aiohttp.ClientSession(proxy=proxy)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()
    
    async def get_direct_link(self, url: str) -> str:
        """Obtiene el enlace directo llamando al resolver gateway."""
        endpoint = f"{DEBRID_GATEWAY}/resolve/?url={url}"
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint) as response:
                response.raise_for_status()
                data = await response.json()
                resolved_url = data.get("url")
                if resolved_url:
                    logger.debug(f"UsersDrive resolved: {resolved_url}")
                    return resolved_url
                else:
                    raise Exception(f"Resolution failed: {data.get('message')}")

    async def get_download_info(self, url: str) -> DownloadInfo:
        """Obtiene información de descarga incluyendo el enlace directo."""
        direct_link = await self.get_direct_link(url)
        filename = "unknown"
        filesize = 0
        
        async with self.session.head(direct_link) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize = int(headers_info['Content-Length'])
            if 'Content-Disposition' in headers_info:
                disp = headers_info['Content-Disposition']
                if 'filename=' in disp:
                    filename = disp.split('filename=')[1].split(';')[0].strip('"')
        
        if filename == "unknown":
            # Intentar extraer del URL
            filename = direct_link.split('/')[-1].split('?')[0]
        
        return DownloadInfo(direct_link, filename, filesize, {})
