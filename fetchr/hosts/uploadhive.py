import aiohttp
from ..host_resolver import AbstractHostResolver
from ..types import DownloadInfo
from bs4 import BeautifulSoup
from fetchr.network import get_random_proxy

class UploadHiveResolver(AbstractHostResolver):
    async def __aenter__(self):
        self.proxy = get_random_proxy()
        self.session = aiohttp.ClientSession(
            proxy=self.proxy
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def _get_id(self, url: str) -> str:
        return url.split("/")[-1]
    
    async def get_download_info(self, url: str) -> DownloadInfo:
        # https://uploadhive.com/z5jdjqaorvbz
        id = self._get_id(url)
        # url endcode post op=download2&id=z5jdjqaorvbz&rand=&referer=&method_free=&method_premium=

        response = await self.session.post(url, data={
            "op": "download2",
            "id": id,
            "rand": "",
            "referer": "",
            "method_free": "",
            "method_premium": "",
        }, headers={
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "es-ES,es;q=0.9",
            "cache-control": "no-cache",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://uploadhive.com",
            "pragma": "no-cache",
            "priority": "u=0, i",
            "referer": f"https://uploadhive.com/{id}",
            "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "same-origin",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        })
        
        response.raise_for_status()
        html = await response.text()
        
        
        NOT_FOUND_MESSAGES = [
            "The file was removed by administrator",
            "removed by administrator"
            "No such file",
            "File not found",
        ]
        
        if any(message in html for message in NOT_FOUND_MESSAGES):
            raise FileNotFoundError("File not found")
        
        soup = BeautifulSoup(html, "html.parser")
        
        anchor = soup.select_one("#direct_link a")
        direct_url = anchor.get("href")
        filename = direct_url.split("/")[-1]
        response = await self.session.get(direct_url)
        response.raise_for_status()
        size = int(response.headers.get("Content-length"))
        return DownloadInfo(direct_url, filename, size, {})