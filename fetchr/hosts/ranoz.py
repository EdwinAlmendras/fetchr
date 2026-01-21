import aiohttp
import re
from dataclasses import dataclass
from typing import Optional
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import asyncio
from fetchr.network import get_aiohttp_proxy_connector
class RanozError(Exception):
    """Base exception for Ranoz operations"""
    pass


class FileNotFoundError(RanozError):
    """Exception raised when file is not found"""
    pass


class InvalidURLError(RanozError):
    """Exception raised when URL format is invalid"""
    pass


class APIError(RanozError):
    """Exception raised when API request fails"""
    pass


@dataclass
class FileInfo:
    id: str
    filename: str
    type: str
    size: int
    url: str
    upload_state: str

class RanozResolver(AbstractHostResolver):
    host = "ranoz.gg"
    def __init__(self):
        self.cdn = "st7"
        self.dl_folder = ""
        self.proxy_auth = ""
        self.proxy_host = ""
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = get_aiohttp_proxy_connector()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        
    async def get_file_info(self, file_id: str) -> FileInfo:
        try:
            async with self.session.get(
                f"https://ranoz.gg/api/v1/files/{file_id}", 
                timeout=10
            ) as response:
                response.raise_for_status()
                import json
                # data can be text or json
                data = await response.text()
                data = json.loads(data)
                print(data)
                if 'data' not in data:
                    raise FileNotFoundError(f"File not found: {file_id}")
                    
                file_data = data['data']
                required_fields = ['id', 'filename', 'type', 'size', 'url', 'upload_state']
                
                for field in required_fields:
                    if field not in file_data:
                        raise APIError(f"Missing field '{field}' in API response")
                        
                return FileInfo(
                    id=file_data['id'],
                    filename=file_data['filename'],
                    type=file_data['type'],
                    size=file_data['size'],
                    url=file_data['url'],
                    upload_state=file_data['upload_state']
                )
        except aiohttp.ClientError as e:
            raise APIError(f"HTTP error while getting file info: {e}")
        except Exception as e:
            raise RanozError(f"Unexpected error while getting file info: {e}")
        
    def _create_endpoint_url(self, file_info: FileInfo) -> str:
        """Creates endpoint URL from file information"""
        return f"{file_info.id}-{file_info.filename}"
    
    async def get_download_info(self, url: str) -> DownloadInfo:
        """Resolves a Ranoz link and returns download information"""
        try:
            # Validate URL format
            if not url or 'ranoz.gg' not in url:
                raise InvalidURLError(f"Invalid Ranoz URL format: {url}")
                
            file_id = url.split('/')[-1]
            if not file_id:
                raise InvalidURLError(f"Could not extract file ID from URL: {url}")
                
            fileinfo = await self.get_file_info(file_id)
            
            # Check if file is ready for download
            if fileinfo.upload_state != 'completed':
                raise FileNotFoundError(f"File not ready for download. State: {fileinfo.upload_state}")
                
            endpoint_url = self._create_endpoint_url(fileinfo)
            filename = fileinfo.filename
            download_url = f"https://{self.cdn}.ranoz.gg/{endpoint_url}"
            
            # Extract CDN from URL if present
            cdn_match = re.search(r'st[1-9]', url)
            if cdn_match:
                download_url = f"https://{cdn_match.group()}.ranoz.gg/{endpoint_url}"
                
            return DownloadInfo(download_url, filename, fileinfo.size)
            
        except (InvalidURLError, FileNotFoundError, APIError, RanozError):
            raise
        except Exception as e:
            raise RanozError(f"Unexpected error while getting download info: {e}")
        
async def main():
    resolver = RanozResolver()
    result = await resolver.get_download_info("https://ranoz.gg/file/1sK69V6X")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
