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

from fetchr.hosts import passtrought
from fetchr.hosts.krakenfiles import KrakenFilesResolver
from fetchr.hosts.sendnow import SendNowResolver
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

UPLOAD_FLIX_HOSTS = ["uploadflix.cc", "uploadflix.net", "uploadflix.com", "1uploadflix.net", "dl.uploadflix.com"]

# 1fichier """ UPLOAD_FLIX_HOSTS + """
SUPPORTED_HOSTS = [ "pixeldrain.com","filedot.to", "ranoz.gg", 
    "gofile.io", "filemirage.com","uploadbay.net", "pomf2.lain.la", "www.upload.ee", "upload.ee",
     "desiupload.co", "send.now", "krakenfiles.com"] +  ["axfc.net", "anonfile.de", "uploadhive.com"] + UPLOAD_FLIX_HOSTS + ["1fichier.com"]

pass_through_hosts = ["uploadbay.net", "clicknupload.net", "clicknupload.click", "pomf2.lain.la"]

HOSTS_HANLDER = {
    "ranoz.gg":  {
        "max_concurrent": 5, 
        "download_with_aria2c": True,
        "max_connections": 5, 
        "resolver": RanozResolver
    }, 
    "st7.ranoz.gg": {
        "download_with_aria2c": True,
        "max_concurrent": 5, 
        "max_connections": 5, 
        "resolver": PassThroughResolver
    },
    "clicknupload.net": {
        "max_concurrent": 1, 
        "max_connections": 5, 
        "resolver": PassThroughResolver
    },
        "clicknupload.net": {
        "max_concurrent": 1, 
        "max_connections": 5, 
        "resolver": PassThroughResolver
    },
    "uploadbay.net": {
        "max_concurrent": 5, 
        "max_connections": 5,
        "download_with_aria2c": True,
        "resolver": PassThroughResolver
    },
    "pomf2.lain.la": {
        "max_concurrent": 5, 
        "max_connections": 5, 
        "download_with_aria2c": True,
        "resolver": PassThroughResolver
    },
    **{
        host: {
            "ignore_ssl": True,
            "max_concurrent": 2,
            "resolver": UploadFlixResolver,
            "max_connections": 10,
        }
        for host in UPLOAD_FLIX_HOSTS
    },
    "anonfile.de": {
        "download_with_aria2c": True,
        "resolver": AnonFileResolver,
        "max_connections": 1, 
    },
    "gofile.io": {
        "max_concurrent": 5,
        "max_connections": 1, 
        "resolver": GofileResolver
    }, # ok
    "1fichier.com": { 
        "download_with_aria2c": True,
        "max_concurrent": 1,
        "max_connections": 1, 
        "resolver": OneFichierResolver
    }, 
    "filedot.to": {
        "ignore_ssl": True,
        "max_concurrent": 5, 
        "max_connections": 1, 
        "resolver": FiledotResolver
    },
    "desiupload.co": {
        "download_with_aria2c": True,
        "max_concurrent": 5, 
        "resolver": DesiUploadResolver
    },
    "pixeldrain.com": {
        "download_with_aria2c": True,
        "max_concurrent": 5, 
        "max_connections": 3, 
        "resolver": PixelDrainResolver
    },
    "axfc.net": {
        "download_with_aria2c": True,
        "use_random_proxy": False,
        "max_connections": 10, 
        "resolver": AxfcResolver
    },
    "filemirage.com": {
        "download_with_aria2c": True,
        "max_concurrent": 5, 
        "max_connections": 5, 
        "resolver": FileMirageResolver
    },
    "upload.ee": {
        "download_with_aria2c": True,
        "max_concurrent": 5, 
        "max_connections": 5, 
        "use_random_proxy": False,
        "resolver": UploadeeResolver
    },
    "uploadhive.com": {
        "max_connections": 1,
        "max_concurrent": 10,
        "download_with_aria2c": True,
        "resolver": UploadHiveResolver,
        "use_random_proxy": False
    }, 
    "send.now": { # SPEED 10MB/s
        "max_connections": 1,
        "max_concurrent": 5,
        "download_with_aria2c": True,
        "resolver": SendNowResolver,
    },
    "krakenfiles.com": { # SPEED 5MB/s
        "max_connections": 10,
        "max_concurrent": 5,
        "download_with_aria2c": True,
        "resolver": KrakenFilesResolver,
    },
    "default": {
        "download_with_aria2c": True,
        "max_connections": 5,
        "resolver": PassThroughResolver,
    }, 
}


MAX_COCURRENT_REQUEST_INFO = 5

concurrent_request_info_semaphore = asyncio.Semaphore(MAX_COCURRENT_REQUEST_INFO)

class Downloader():
    def __init__(self, max_concurrent_global = 20):
        self.chunk_size = CHUNK_SIZE
        self.parallel_downloader = ParallelDownloader()
        self.aria2c_downloader = Aria2cDownloader()
        self.semaphores = {}
        self.max_concurrent_global = max_concurrent_global
        self.global_sempaphore = asyncio.Semaphore(self.max_concurrent_global)
        for key, item in HOSTS_HANLDER.items():
            max_concurrent = item.get("max_concurrent")
            if max_concurrent:
                logger.debug(f"Creating semaphore for {key} -> {max_concurrent}")
                self.semaphores[key] = asyncio.Semaphore(max_concurrent)
        
        
    def _get_host(self, url: str):
        parsed_url = urlparse(url)
        host = parsed_url.netloc
        host = host.lower()
        if host.startswith('www.'):
            host = host[4:]
        return host
        
    async def  download_file(self, url: str, download_dir, callback_progress: Callable[[int, int], None] = lambda a, b: None, solve_captcha: Callable[[str], Awaitable[None]] = None) -> str:
        if "st1.ranoz.gg" in url:
            # replace to st7
            url = url.replace("st1.ranoz.gg", "st7.ranoz.gg")
        
        host = self._get_host(url)
        
        if host not in HOSTS_HANLDER:
            HOST_MANAGER = HOSTS_HANLDER["default"]
        else:
            HOST_MANAGER = HOSTS_HANLDER[host]
        resolver = HOST_MANAGER["resolver"]()
        
        download_info: DownloadInfo = None
        logger.info(f"Host detected: {host}")
        async with resolver as resolver:
            logger.debug(f"Getting download info for {url}")
            async with concurrent_request_info_semaphore:
                download_info = await resolver.get_download_info(url)
            logger.debug(f"Download info: {download_info}")
        if isinstance(download_info, list):
            logger.debug(f"download info its a list {len(download_info)}")
            tasks = []
            for dl_info in download_info:
                options = self._get_options(HOST_MANAGER, download_dir, dl_info, resolver, callback_progress)
                task = asyncio.create_task(self.process_download(options, host, download_dir, dl_info))
                tasks.append(task)
            await asyncio.gather(*tasks)
        else:
            options = self._get_options(HOST_MANAGER, download_dir, download_info, resolver, callback_progress)
            logger.debug("download info its not alist")
            await self.process_download(options, host, download_dir, download_info)
            
    async def process_download(self, options, host, download_dir, download_info):
        if self.check_exists(download_dir, download_info):
            return True
        host_semapthore = self.semaphores.get(host, None)
        async with self.global_sempaphore:
            if host_semapthore:
                logger.debug(f"Applying host semaphore to -> {host}")
                async with host_semapthore:
                    return await self.start_download(options)
            else:
                logger.debug(f"Not mathced sempahore satysayng this host")
                return await self.start_download(options)
    
    def check_exists(self, download_dir, download_info):
        if download_info.filename and download_dir.joinpath(download_info.filename).exists():
            if download_info.size == download_dir.joinpath(download_info.filename).stat().st_size:
                logger.info(f"File {download_info.filename} already exists and size is the same")
                return True
            else:
                logger.info(f"File {download_info.filename} already exists and size is different")
                return False
    
    
    def _get_options(self, HOST_MANAGER, download_dir, download_info, resolver, callback_progress):
         return {
            "max_connections": HOST_MANAGER.get("max_connections", 5),
            "download_with_aria2c": HOST_MANAGER.get("download_with_aria2c", False),
            "use_random_proxy": HOST_MANAGER.get("use_random_proxy", True),
            "ignore_ssl": HOST_MANAGER.get("ignore_ssl", False),
            "download_dir": Path(download_dir),
            "download_info": download_info,
            "callback_progress": callback_progress,
            "aria2c_parallel": HOST_MANAGER.get("aria2c_parallel", False),
            "resolver": resolver
        }   
                
    async def start_download(self, options):
        if options["download_with_aria2c"]:
            options["download_dir"].mkdir(parents=True, exist_ok=True)
            output_path = options["download_dir"] / options["download_info"].filename
            return await self.aria2c_downloader.download(
                options["download_info"], 
                output_path=output_path,
                ignore_ssl=options["ignore_ssl"], 
                use_connections=options["max_connections"],
                max_connections=options["max_connections"],
                max_concurrent_downloads=options["max_connections"],
                use_random_proxy=options["use_random_proxy"],
                proxy=options["resolver"].proxy if hasattr(options["resolver"], "proxy") else None,
            )
        else:
            result = await self.download_to_local(
                options["download_info"], 
                options["download_dir"], 
                callback_progress=options["callback_progress"], 
                ignore_ssl=options["ignore_ssl"],
                chunk_size=self.chunk_size,
                session=options["resolver"].session if hasattr(options["resolver"], "session") else None,
                parallel_connections=options["max_connections"],
                use_random_proxy=options["use_random_proxy"],
                download_with_aria2c=options["aria2c_parallel"],
            )
            return result

     
    
    async def download_to_local(
        self, 
        download_info: DownloadInfo,
        downloads_dir: Path, 
        chunk_size: int = CHUNK_SIZE, 
        retries: int = 3,
        callback_progress: Callable[[int, int], None] = None,
        ignore_ssl: bool = False,
        session: aiohttp.ClientSession = None,
        parallel_connections: int = 1,
        use_random_proxy: bool = False,
        download_with_aria2c: bool = False
    ) -> Optional[str]:
        print(f"Downloading url: {download_info.download_url}")
        try:
            if isinstance(downloads_dir, str):
                downloads_dir = Path(downloads_dir)
            if use_random_proxy:
                from fetchr.network import get_aiohttp_proxy_connector
                session = get_aiohttp_proxy_connector()
            else:
                session = aiohttp.ClientSession()
                
            response = None
            file_handle = None
            
            if parallel_connections > 1:
                # verifu if range request its supported with head
                response = await session.head(download_info.download_url, ssl=False if ignore_ssl else True)
                # accept-ranges = bytes
                exceptions_websites = ["axfc.net"]
                expection_validated = False
                for exception in exceptions_websites:
                    if exception in download_info.download_url:
                        expection_validated = True
                        break
                if not expection_validated:
                    if "accept-ranges" not in response.headers or response.headers["accept-ranges"] != "bytes":
                        raise Exception("Range request not supported")
                
                print(f"Downloading {download_info.download_url}, with parallel connections: {parallel_connections}")
                return await self.parallel_downloader._download_parallel(
                    download_info, 
                    downloads_dir, 
                    download_info.size, 
                    parallel_connections, 
                    session, 
                    callback_progress, 
                    chunk_size, 
                    ignore_ssl,
                    use_random_proxy,
                    download_with_aria2c
                )
            else:
                console.print(f"Downloading {download_info.download_url}, with ignore_ssl: {ignore_ssl}")
                response = await session.get(
                    download_info.download_url, 
                    headers=download_info.headers or {}, 
                    ssl=False if ignore_ssl else True,
                )
                
                response.raise_for_status()
                
                local_path = downloads_dir.joinpath(download_info.filename)

                logger.info(f"Downloading {download_info.filename} from {download_info.download_url}, size: {download_info.size}, local path: {local_path}, chunk size: {chunk_size}")
                
                downloaded = 0
                last_callback = 0
                
                async with aiofiles.open(local_path, "wb") as file_handle:
                    async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                        await file_handle.write(chunk)
                        downloaded += len(chunk)
                        now = time.monotonic()
                        if callback_progress and now - last_callback >= 1:
                            await callback_progress(downloaded, download_info.size)
                            last_callback = now

                if file_handle:
                    print(f"Closing file handle", file_handle)
                    await file_handle.close()
                if session:
                    print(f"Closing session", session)
                    await session.close()
                            
                if download_info.size and downloaded < download_info.size:
                    raise Exception("Incomplete download")

                return local_path
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
    def _extract_filename(self, response: aiohttp.ClientResponse, url: str) -> str:
        """Get filename from headers or fallback."""
        cd = response.headers.get("content-disposition")
        if cd and "filename=" in cd:
            return cd.split("filename=")[1].strip('" ')
        return os.path.basename(url) 

