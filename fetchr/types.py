from dataclasses import dataclass, field

class FileDeletedError(Exception):
    pass

@dataclass 
class DownloadInfo:
    download_url: str
    filename: str
    size: int
    headers: dict = field(default_factory=dict)