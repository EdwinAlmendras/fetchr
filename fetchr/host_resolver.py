from abc import ABC, abstractmethod
from fetchr.types import DownloadInfo

class AbstractHostResolver(ABC):
    @abstractmethod
    def get_download_info(self, url: str) -> DownloadInfo:
        pass