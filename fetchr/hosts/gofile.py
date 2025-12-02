import aiohttp
from dataclasses import dataclass
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import logging
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

class GofileResolver(AbstractHostResolver):
    def __init__(self):
        self.base_url = "https://api.gofile.io"
        self.session = None
        self.token = None
        self.token_obtained = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get_token(self, force_new: bool = False) -> str:
        """Gets a token from GoFile API"""
        if self.token_obtained and self.token and not force_new:
            return self.token
        
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        try:
            async with self.session.post(f"{self.base_url}/accounts") as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("status") == "ok":
                    self.token = data["data"]["token"]
                    self.token_obtained = True
                    return self.token
                else:
                    raise TokenError(f"Failed to get token: {data.get('status')}")
        except aiohttp.ClientError as e:
            raise TokenError(f"HTTP error while getting token: {e}")
        except Exception as e:
            raise TokenError(f"Unexpected error while getting token: {e}")

    async def _get_file_info(self, file_id: str) -> FileInfo:
        """Gets information about a file or folder in GoFile"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}/contents/{file_id}?wt=4fd6sg89d7s6&token={self.token}"
        print(f"url: {url}")
        async with self.session.get(url, headers={"Cookie": f"accountToken={self.token};path=/;domain=gofile.io;SameSite=Lax;Secure;"}) as response:
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
        
        if not self.token:
            self.token = await self._get_token()
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
                        "Cookie": f"accountToken={self.token}"
                    }
                )
                dl_infos.append(dl_info)
            return dl_infos
        
        return DownloadInfo(
            file_info.link, 
            file_info.name, 
            file_info.size, 
            {
                "Cookie": f"accountToken={self.token}"
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
