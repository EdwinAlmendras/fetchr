import aiohttp
from dataclasses import dataclass
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import logging
import asyncio
import datetime
from typing import Optional, Union, List

logger = logging.getLogger("downloader.gofile")

class GoFileError(Exception):
    """Base exception for GoFile operations"""
    pass


class TokenError(GoFileError):
    """Exception raised when token operations fail"""
    pass


class FileNotFoundError(GoFileError):
    """Exception raised when file is not found"""
    pass


class InvalidURLError(GoFileError):
    """Exception raised when URL format is invalid"""
    pass


@dataclass
class FileInfo:
    id: str
    name: str
    type: str
    size: int
    link: str
    headers: dict


class _GoFileTokenManager:
    """Singleton-style token manager for GoFile API.

    Caches a token and reuses it until TTL expires. Uses an async lock
    to avoid concurrent token requests.
    """
    def __init__(self, base_url: str = "https://api.gofile.io", ttl_seconds: int = 3600):
        self.base_url = base_url
        self._token: Optional[str] = None
        self._obtained_at: Optional[datetime.datetime] = None
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_token(self, force_new: bool = False) -> str:
        async with self._lock:
            if not force_new and self._token and self._obtained_at:
                age = (datetime.datetime.utcnow() - self._obtained_at).total_seconds()
                if age < self._ttl:
                    return self._token

            if not self._session:
                self._session = aiohttp.ClientSession()

            try:
                async with self._session.post(f"{self.base_url}/accounts") as response:
                    response.raise_for_status()
                    data = await response.json()
                    if data.get("status") == "ok":
                        self._token = data["data"]["token"]
                        self._obtained_at = datetime.datetime.utcnow()
                        return self._token
                    else:
                        raise TokenError(f"Failed to get token: {data.get('status')}")
            except aiohttp.ClientError as e:
                raise TokenError(f"HTTP error while getting token: {e}")
            except Exception as e:
                raise TokenError(f"Unexpected error while getting token: {e}")

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None


# module-level manager instance (acts as singleton)
_gofile_token_manager = _GoFileTokenManager()

class GofileResolver(AbstractHostResolver):
    def __init__(self):
        self.base_url = "https://api.gofile.io"
        # resolver-specific session (used for content requests)
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_token(self, force_new: bool = False) -> str:
        """Delegate token retrieval to the module-level token manager."""
        return await _gofile_token_manager.get_token(force_new=force_new)

    async def _get_file_info(self, file_id: str) -> FileInfo:
        """Gets information about a file or folder in GoFile"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        referer = "https://gofile.io/"
        url = f"{self.base_url}/contents/{file_id}?contentFilter=&page=1&pageSize=1000&sortField=name&sortDirection=1"
        print(f"url: {url}")
        # get shared token from the singleton manager
        token = await _gofile_token_manager.get_token()
        headers={"Authorization": f"Bearer {token}", "Referer": referer, "X-Website-Token": "4fd6sg89d7s6"}
        print(f"headers: {headers}")
        async with self.session.get(url, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            if data.get("status") != "ok":
                raise aiohttp.ClientResponseError(request_info=response.request_info, history=response.history, status=404, message=f"File not found: {data.get('status')}")

            info = data["data"]
            if info.get("type") == "folder":
                # Take the first file inside the folder
                files = []
                for child in info.get("children", {}).values():
                    if child.get("type") == "file":
                        file_info = FileInfo(
                            id=child["id"],
                            name=child["name"],
                            type=child["type"],
                            size=int(child["size"]),
                            link=child["link"],
                            headers=response.headers
                        )
                        files.append(file_info)
                return files
            elif info.get("type") == "file":
                return FileInfo(
                    id=info["id"],
                    name=info["name"],
                    type=info["type"],
                    size=int(info["size"]),
                    link=info["link"],
                    headers=response.headers
                )
            else:
                raise aiohttp.ClientResponseError(request_info=response.request_info, history=response.history, status=404, message=f"Unknown file type: {info.get('type')}")


    async def get_download_info(self, url: str) -> DownloadInfo:
        """Resolves a GoFile link and returns download information"""
        # ensure we have a valid token (manager caches/reuses it)
        token = await self._get_token()
            # Extract ID from URL
        if "/d/" not in url:
            raise InvalidURLError(f"Invalid GoFile URL format: {url}")
        file_id = url.split("/d/")[-1].split("/")[0].split("?")[0]
        file_info = await self._get_file_info(file_id)
        
        if isinstance(file_info, list):
            dl_infos = []
            for file in file_info:
                dl_info = DownloadInfo(
                    file.link, 
                    file.name, 
                    file.size, 
                    {
                        "Cookie": f"accountToken={token}"
                    }
                )
                dl_infos.append(dl_info)
            return dl_infos
        
        return DownloadInfo(
            file_info.link, 
            file_info.name, 
            file_info.size, 
            {
                "Cookie": f"accountToken={token}"
            }
        )

import asyncio

if __name__ == "__main__":

    async def main():
        resolver = GofileResolver()
        
        async with resolver as resolver:
            download_info = await resolver.get_download_info("https://gofile.io/d/CY20kP")
            print(download_info)

    asyncio.run(main())
