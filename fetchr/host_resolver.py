from abc import ABC, abstractmethod
from fetchr.types import DownloadInfo

class AbstractHostResolver(ABC):
    @classmethod
    @abstractmethod
    def match(cls, url: str) -> bool:
        pass

    @abstractmethod
    async def get_download_info(self, url: str) -> DownloadInfo:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass