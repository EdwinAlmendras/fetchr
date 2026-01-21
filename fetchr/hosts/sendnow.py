import asyncio
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import cloudscraper

class SendNowResolver(AbstractHostResolver):
    host = "send.now"
    def __init__(self, timeout: int = 5):
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
        }
        self.scraper = None

    async def __aenter__(self):
        self.scraper = cloudscraper.create_scraper()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # cloudscraper doesn't have a close method, but we can reset the scraper
        self.scraper = None

    @staticmethod
    def get_id(url: str) -> str:
        return url.split("/")[-1]
    
    async def get_download_info(self, url: str) -> DownloadInfo:
        form_data = {
            'op': 'download2',
            'id': self.get_id(url),
            'rand': '',
            'referer': '',
            'method_free': '',
            'method_premium': '',
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        
        # Execute cloudscraper calls in a thread to keep async interface
        loop = asyncio.get_event_loop()
        
        # POST request should be redirected to the direct url
        response = await loop.run_in_executor(
            None, 
            lambda: self.scraper.post(url, data=form_data, headers=headers, allow_redirects=False, timeout=self.timeout)
        )
        response.raise_for_status()
        redirect_url = response.headers.get("Location")
        
        if not redirect_url:
            raise ValueError("No redirect URL found in response")
        
        # HEAD request to get file info
        head_response = await loop.run_in_executor(
            None,
            lambda: self.scraper.head(redirect_url, timeout=self.timeout)
        )
        head_response.raise_for_status()
        filesize = int(head_response.headers.get("Content-Length", 0))
        filename = redirect_url.split("/")[-1]
        
        return DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=redirect_url,
            headers={},
        )