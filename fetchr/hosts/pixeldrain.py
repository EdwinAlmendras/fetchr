import aiohttp
from fetchr.types import DownloadInfo
from fetchr.host_resolver import AbstractHostResolver
from fetchr.resolver import get_direct_link

class PixelDrainResolver(AbstractHostResolver):
    def __init__(self, timeout: int = 5):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Upgrade-Insecure-Requests': '1',
        }
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=self.timeout,
            headers=self.headers,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            await self.__aenter__()
            
        url = url.replace("/u/", "/api/file/")
        
        async with self.session.head(url, timeout=30) as response:
            headers_info = dict(response.headers)
            if 'Content-Length' in headers_info:
                filesize_bytes = int(headers_info['Content-Length'])
                filesize = filesize_bytes
            if 'Content-Disposition' in headers_info:
                filename = headers_info['Content-Disposition'].split('filename=')[1].split(';')[0].strip('"')

        async with self.session.get(url, timeout=30) as response:
            try:
                data = await response.json()
                if not data['success']:
                    message = data['message']
                    if message == "file_rate_limited_captcha_required":
                        direct_link = await get_direct_link(url)
                    else:
                        raise Exception(message)
                else:
                    direct_link = url
            except:
                direct_link = url
        
        download_info = DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=direct_link,
            headers=response.headers,
        )
        return download_info
    
