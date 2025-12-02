from pathlib import Path
import asyncio
from typing import Callable, Optional
import os
import aiohttp
import aiofiles
from urllib.parse import urlparse
from typing import Awaitable
import logging
import time
from functools import partial
from aiohttp_socks.connector import _ResponseHandler
from rich.console import Console

from fetchr.hosts.ranoz import RanozResolver
from fetchr.hosts.anonfile import AnonFileResolver
from fetchr.hosts.gofile import GofileResolver
from fetchr.hosts.passtrought import PassThroughResolver
from fetchr.hosts.uploadflix import UploadFlixResolver
from fetchr.hosts.onefichier import OneFichierResolver
from fetchr.hosts.filedot import FiledotResolver
from fetchr.hosts.desiupload import DesiUploadResolver
from fetchr.hosts.pixeldrain import PixelDrainResolver
from fetchr.hosts.axfc import AxfcResolver
from fetchr.hosts.filemirage import FileMirageResolver
from fetchr.hosts.uploadhive import UploadHiveResolver
from fetchr.hosts.uploadee import UploadeeResolver
from fetchr.types import DownloadInfo
import subprocess
from fetchr.parallel import ParallelDownloader
from fetchr.aria2c import Aria2cDownloader
anonfile_locker = asyncio.Lock()
from rich import print


console = Console()
logger = logging.getLogger("downloader")

CHUNK_SIZE = 4 * 1024 * 1024

UPLOAD_FLIX_HOSTS = ["uploadflix.cc", "uploadflix.net", "uploadflix.com", "1uploadflix.net"]

# 1fichier """ UPLOAD_FLIX_HOSTS + """
SUPPORTED_HOSTS = [ "pixeldrain.com","filedot.to", "ranoz.gg",
    "gofile.io", "filemirage.com","uploadbay.net", "pomf2.lain.la", "upload.ee", 
     "desiupload.co"] +  ["axfc.net", "anonfile.de", "uploadhive.com"]



class Downloader():
    def __init__(self):
        
        self.upload_flix_hosts = UPLOAD_FLIX_HOSTS
        pass_through_hosts = ["uploadbay.net", "clicknupload.net", "pomf2.lain.la"]
        self.resolvers = {
            "ranoz.gg": RanozResolver, 
            "st7.ranoz.gg": PassThroughResolver,
            "upload.ee": UploadeeResolver,
            "anonfile.de": AnonFileResolver,
            "gofile.io": GofileResolver, # ok
            **{host: PassThroughResolver for host in pass_through_hosts},
            **{host: UploadFlixResolver for host in self.upload_flix_hosts},
            "1fichier.com": OneFichierResolver, # 50kbs
            "filedot.to": FiledotResolver,
            "desiupload.co": DesiUploadResolver,
            "pixeldrain.com": PixelDrainResolver,
            "axfc.net": AxfcResolver,
            "filemirage.com": FileMirageResolver,
            "uploadhive.com": UploadHiveResolver, # USE SAME IP 
            "default": PassThroughResolver,
            
        }
        self.chunk_size = CHUNK_SIZE
        self.parallel_downloader = ParallelDownloader()
        self.aria2c_downloader = Aria2cDownloader()
        
            
    async def download_file(self, url: str, download_dir, callback_progress: Callable[[int, int], None] = lambda a, b: None, solve_captcha: Callable[[str], Awaitable[None]] = None) -> str:
        download_dir = Path(download_dir)
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        logger.debug(f"Downloading {url} from {host}")
        if host.startswith('www.'):
            host = host[4:]
        if host not in self.resolvers:
            resolver_class = self.resolvers["default"]
        else:
            resolver_class = self.resolvers[host]
        ignore_ssl = True
        resolver = resolver_class()
        parallel_connections = 1
        use_random_proxy = True
        download_info: DownloadInfo = None
        number_of_parts = 1
        proxy = None
        async with resolver as resolver:
            download_info = await resolver.get_download_info(url)
        if download_info.filename and download_dir.joinpath(download_info.filename).exists():
            if download_info.size == download_dir.joinpath(download_info.filename).stat().st_size:
                logger.debug(f"File {download_info.filename} already exists and size is the same")
                print(f"[green]File {download_info.filename} already exists and size is the same [/green]")
                return download_dir.joinpath(download_info.filename)
            else:
                logger.debug(f"File {download_info.filename} already exists and size is different")
                print(f"[red]File {download_info.filename} already exists and size is different [/red]")
        download_dir.mkdir(parents=True, exist_ok=True)
        output_path = download_dir / download_info.filename
        logger.debug(f"Downloading {download_info.filename} to {output_path}")
        return await self.aria2c_downloader.download(
            download_info, 
            output_path=output_path,
            ignore_ssl=ignore_ssl, 
            use_connections=parallel_connections,
            max_connections=parallel_connections,
            max_concurrent_downloads=number_of_parts,
            use_random_proxy=use_random_proxy,
            proxy=proxy,
        )