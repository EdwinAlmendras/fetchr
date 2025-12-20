from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import aiohttp
from fetchr.network import get_tor_client
import logging
from urllib.parse import unquote
logger = logging.getLogger("downloader.passtrought")


REDIRECT_HOSTS = [
    "sd2y3ekfioqfag45vmufbcezz44jfdz4ihefmogjfjih5sadmbmxzaid.onion", 
    "cpftwf66tdxnhrtau6t4hvm5sznlglv4r4ha5uxmc7ulhmcgry3mttyd"
]


class PassThroughResolver(AbstractHostResolver):
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str, *args, **kwargs) -> DownloadInfo:
        client = get_tor_client() if "onion" in url else self.session
        logger.info(f"Getting download info for url: {url}, check protector host: {REDIRECT_HOSTS}")
        if any(host in url for host in REDIRECT_HOSTS):
            logger.info("URL match in protectors")
            response = await client.get(url)
            url = str(response.url)
            logger.info(f"Resolved url: {url} by redirect")
            client = self.session
        
        response = await client.head(url, *args, **kwargs)
        # if response code 405     
        if response.status == 405:
            logger.warning(f"405 error, requesting url: {url}")
            response = await client.get(url, *args, **kwargs)
            
        response.raise_for_status()
        content_disp = response.headers.get("Content-Disposition")

        filename = None
        if content_disp:
            cdl = content_disp.lower()
            # Prefer RFC 5987 filename* parameter, e.g. filename*=UTF-8''prasped.7z.004
            if "filename*=" in cdl:
                try:
                    # Extract the raw value after filename*=
                    raw_part = content_disp.split("filename*=", 1)[1].split(";", 1)[0].strip()
                    # Remove surrounding quotes if present
                    if raw_part.startswith('"') and raw_part.endswith('"'):
                        raw_part = raw_part[1:-1]
                    # Format: charset''urlencoded-filename
                    # Example: UTF-8''prasped.7z.004
                    if "''" in raw_part:
                        _, encoded_name = raw_part.split("''", 1)
                    else:
                        encoded_name = raw_part
                    filename = unquote(encoded_name)
                except Exception as e:
                    logger.warning(f"failed to parse filename* from Content-Disposition: {e}")
                    filename = None
            # Fallback to simple filename=
            if not filename and "filename=" in cdl:
                try:
                    raw_part = content_disp.split("filename=", 1)[1].split(";", 1)[0].strip()
                    if raw_part.startswith('"') and raw_part.endswith('"'):
                        raw_part = raw_part[1:-1]
                    filename = raw_part
                except Exception as e:
                    logger.warning(f"failed to parse filename from Content-Disposition: {e}")
                    filename = None

        if not filename:
            filename = url.rstrip("/").split("/")[-1]

        size = int(response.headers.get("Content-Length", "0"))
        return DownloadInfo(url, filename, size, {})

    
