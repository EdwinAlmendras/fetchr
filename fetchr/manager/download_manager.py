import asyncio
import logging
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import select

from fetchr.database.session import init_db, SessionLocal
from fetchr.database.models import Package, File
from fetchr.aria2_daemon import Aria2DaemonManager
from fetchr.config_loader import load_hosts_config
from fetchr.types import DownloadInfo

logger = logging.getLogger(__name__)

# Load host configuration
_config_data = load_hosts_config()
HOSTS_HANDLER = _config_data["hosts_handler"]


class DownloadManager:
    def __init__(self, download_root: Path):
        self.download_root = download_root
        self.aria2 = Aria2DaemonManager(download_dir=download_root)
        self.running = False
        self._sync_task = None

    async def start(self):
        """Initialize DB and Aria2 connection."""
        init_db()
        await self.aria2.initialize()
        self.running = True
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info("🚀 DownloadManager started")

    async def stop(self):
        self.running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

    def _get_host(self, url: str) -> str:
        """Extract host from URL."""
        parsed_url = urlparse(url)
        host = parsed_url.netloc.lower()
        if host.startswith('www.'):
            host = host[4:]
        return host

    def _get_host_config(self, host: str) -> dict:
        """Get host configuration, fallback to default."""
        if host in HOSTS_HANDLER:
            return HOSTS_HANDLER[host]
        return HOSTS_HANDLER.get("default", {})

    async def _resolve_url(self, url: str) -> tuple[DownloadInfo, dict]:
        """
        Resolve a URL using the appropriate host resolver.
        Returns (DownloadInfo, host_config).
        """
        host = self._get_host(url)
        host_config = self._get_host_config(host)

        resolver_class = host_config.get("resolver")
        if not resolver_class:
            raise ValueError(f"No resolver found for host: {host}")

        resolver = resolver_class()

        async with resolver:
            download_info = await resolver.get_download_info(url)

        return download_info, host_config

    def create_package(self, name: str, parent_id: Optional[int] = None) -> Package:
        """Create a new package (folder structure)."""
        session = SessionLocal()
        try:
            path = self.download_root / name
            if parent_id:
                parent = session.get(Package, parent_id)
                if parent:
                    path = Path(parent.path) / name

            path.mkdir(parents=True, exist_ok=True)

            pkg = Package(
                name=name,
                path=str(path),
                parent_id=parent_id,
                status="ACTIVE"
            )
            session.add(pkg)
            session.commit()
            session.refresh(pkg)
            return pkg
        finally:
            session.close()

    async def add_file_to_package(
        self,
        package_id: int,
        url: str,
        filename: str = None,
        resolve: bool = True
    ) -> List[File]:
        """
        Add a file to a package and start downloading with Aria2.

        Args:
            package_id: Target package ID
            url: URL to download (can be host URL like gofile.io/d/xxx)
            filename: Override filename (optional)
            resolve: Whether to resolve URL through host resolver (default True)

        Returns:
            List of File records created
        """
        session = SessionLocal()
        try:
            package = session.get(Package, package_id)
            if not package:
                raise ValueError(f"Package {package_id} not found")

            download_infos = []
            host_config = {}

            if resolve:
                try:
                    result, host_config = await self._resolve_url(url)
                    if isinstance(result, list):
                        download_infos = result
                    else:
                        download_infos = [result]
                except Exception as e:
                    logger.error(f"Failed to resolve URL {url}: {e}")
                    raise
            else:
                if not filename:
                    filename = url.split("/")[-1]
                download_infos = [DownloadInfo(
                    download_url=url,
                    filename=filename,
                    size=0,
                    headers={}
                )]

            created_files = []

            for dl_info in download_infos:
                final_filename = filename if filename else dl_info.filename

                file_record = File(
                    package_id=package.id,
                    url=url,
                    filename=final_filename,
                    status="QUEUED",
                    size_bytes=dl_info.size or 0
                )
                session.add(file_record)
                session.commit()
                session.refresh(file_record)

                try:
                    download_options = {
                        "dir": str(package.path),
                        "out": final_filename
                    }

                    # Add headers if the host requires them
                    if host_config.get("use_headers", False) and dl_info.headers:
                        header_list = [f"{k}: {v}" for k, v in dl_info.headers.items()]
                        download_options["header"] = header_list

                    # Add connection settings from host config
                    max_connections = host_config.get("max_connections", 5)
                    download_options["split"] = str(max_connections)
                    download_options["max-connection-per-server"] = str(max_connections)

                    # Ignore SSL if configured
                    if host_config.get("ignore_ssl", False):
                        download_options["check-certificate"] = "false"

                    gid = self.aria2.add_download(
                        dl_info.download_url,
                        options=download_options
                    )

                    file_record.aria2_gid = gid
                    file_record.status = "DOWNLOADING"
                    session.commit()
                    logger.info(f"➕ Added download: {final_filename} (GID: {gid})")

                except Exception as e:
                    file_record.status = "ERROR"
                    session.commit()
                    logger.error(f"Failed to add download to Aria2: {e}")
                    raise

                created_files.append(file_record)

            return created_files if len(created_files) > 1 else created_files[0]

        finally:
            session.close()

    async def analyze_links(self, package_id: int, urls: List[str]) -> List[File]:
        """
        Analyze links and add them to a GRABBER package.
        Package.status = "GRABBER", File.status = "QUEUED" (ok) or "ERROR" (failed).
        """
        session = SessionLocal()
        created_files = []
        try:
            package = session.get(Package, package_id)
            if not package:
                raise ValueError(f"Package {package_id} not found")

            # Mark package as GRABBER
            package.status = "GRABBER"

            for url in urls:
                url = url.strip()
                if not url:
                    continue
                    
                try:
                    result, _ = await self._resolve_url(url)
                    infos = result if isinstance(result, list) else [result]

                    for info in infos:
                        file_record = File(
                            package_id=package.id,
                            url=url,
                            filename=info.filename,
                            status="QUEUED",
                            size_bytes=info.size or None
                        )
                        session.add(file_record)
                        created_files.append(file_record)
                        logger.info(f"Analyzed {info.filename} ({info.size or 'unknown'} bytes)")
                        
                except Exception as e:
                    # Resolution failed - create ERROR file with message
                    error_msg = str(e)
                    file_record = File(
                        package_id=package.id,
                        url=url,
                        filename=f"UNKNOUN",
                        status="ERROR",
                        size_bytes=None,
                        error_message=error_msg
                    )
                    session.add(file_record)
                    created_files.append(file_record)
                    logger.error(f"✗ Failed to analyze {url}: {error_msg}")
            
            session.commit()
            for f in created_files:
                session.refresh(f)
                
            return created_files
        finally:
            session.close()

    async def start_downloads(self, file_ids: List[int]) -> List[File]:
        """Start downloads for specific file IDs."""
        # ... implementation remains same, useful for selective start ...
        return await self._start_files_internal(file_ids)

    async def start_package_downloads(self, package_id: int) -> List[File]:
        """Start all QUEUED files in a GRABBER package and activate the package."""
        session = SessionLocal()
        try:
            package = session.get(Package, package_id)
            if not package:
                return []
            
            # Get all QUEUED files in package
            files = session.execute(
                select(File).where(File.package_id == package_id, File.status == "QUEUED")
            ).scalars().all()
            
            file_ids = [f.id for f in files]
            
            # Change package status to ACTIVE
            package.status = "ACTIVE"
            session.commit()
            
            if not file_ids:
                return []
                
            return await self._start_files_internal(file_ids)
        finally:
            session.close()

    async def _start_files_internal(self, file_ids: List[int]) -> List[File]:
        """Internal method to start downloads given a list of IDs."""
        session = SessionLocal()
        started_files = []
        try:
            files = session.execute(select(File).where(File.id.in_(file_ids))).scalars().all()
            logger.info(f"Starting {len(files)} files: {file_ids}")
            
            for file_record in files:
                if file_record.status not in ["QUEUED", "ERROR"]:
                    logger.debug(f"Skipping file {file_record.id} - status is {file_record.status}")
                    continue
                    
                package = session.get(Package, file_record.package_id)
                if not package:
                    logger.warning(f"Package not found for file {file_record.id}")
                    continue

                try:
                    host = self._get_host(file_record.url)
                    host_config = self._get_host_config(host)
                    logger.debug(f"Resolving {file_record.url} for host {host}")
                    
                    # Try to re-resolve for fresh download URL
                    try:
                        dl_info, host_config = await self._resolve_url(file_record.url)
                        logger.debug(f"Resolved OK: {dl_info}")
                    except Exception as resolve_error:
                        logger.error(f"Re-resolve failed for {file_record.url}: {resolve_error}")
                        file_record.status = "ERROR"
                        file_record.error_message = f"Re-resolve failed: {resolve_error}"
                        continue

                    # Match by filename if resolver returns list
                    match_info = None
                    if isinstance(dl_info, list):
                        for info in dl_info:
                            if info.filename == file_record.filename:
                                match_info = info
                                break
                    else:
                        match_info = dl_info

                    if not match_info:
                        logger.error(f"Could not match file {file_record.filename} in resolved info")
                        file_record.status = "ERROR"
                        file_record.error_message = "Could not match file in resolved info"
                        continue
                    
                    download_options = {
                        "dir": str(package.path),
                        "out": file_record.filename,
                        "split": str(host_config.get("max_connections", 5)),
                        "max-connection-per-server": str(host_config.get("max_connections", 5))
                    }
                    
                    if host_config.get("use_headers", False) and match_info.headers:
                        header_list = [f"{k}: {v}" for k, v in match_info.headers.items()]
                        download_options["header"] = header_list
                        
                    if host_config.get("ignore_ssl", False):
                        download_options["check-certificate"] = "false"

                    logger.info(f"Adding to aria2: {match_info.download_url}")
                    gid = self.aria2.add_download(match_info.download_url, options=download_options)
                    
                    file_record.aria2_gid = gid
                    file_record.status = "DOWNLOADING"
                    file_record.error_message = None
                    package.status = "ACTIVE"
                    
                    started_files.append(file_record)
                    logger.info(f"▶ Started download: {file_record.filename} (GID: {gid})")

                except Exception as e:
                    file_record.status = "ERROR"
                    file_record.error_message = str(e)
                    logger.error(f"Failed to start download {file_record.id}: {e}")

            session.commit()
            logger.info(f"Started {len(started_files)} downloads")
            return started_files
        finally:
            session.close()

    async def _sync_loop(self):
        """Periodically sync status from Aria2 to Database."""
        while self.running:
            try:
                await self._sync_one_pass()
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
            await asyncio.sleep(2)

    async def _sync_one_pass(self):
        session = SessionLocal()
        try:
            active_files = session.execute(
                select(File).where(File.status.in_(["DOWNLOADING", "QUEUED", "PAUSED"]))
            ).scalars().all()

            for file_record in active_files:
                gid = file_record.aria2_gid
                filename = file_record.filename

                if not gid:
                    continue

                aria_status = self.aria2.get_status(gid)
                if not aria_status:
                    if file_record.status == "DOWNLOADING":
                        logger.warning(f"GID {gid} not found in Aria2. Marking as ERROR.")
                        file_record.status = "ERROR"
                    continue

                status_map = {
                    "active": "DOWNLOADING",
                    "waiting": "QUEUED",
                    "paused": "PAUSED",
                    "error": "ERROR",
                    "complete": "COMPLETED",
                    "removed": "CANCELLED"
                }

                new_status = status_map.get(aria_status.status, "UNKNOWN")
                file_record.status = new_status

                if aria_status.total_length > 0:
                    file_record.size_bytes = aria_status.total_length
                    file_record.downloaded_bytes = aria_status.completed_length

                if aria_status.error_code:
                    file_record.error_message = aria_status.error_message
                    logger.error(f"Download error for {filename}: {aria_status.error_message}")

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Sync error: {e}")
        finally:
            session.close()

    def get_packages(self) -> List[Package]:
        session = SessionLocal()
        try:
            return session.execute(select(Package)).scalars().all()
        finally:
            session.close()

    def get_files(self, package_id: int = None) -> List[File]:
        """Get files, optionally filtered by package."""
        session = SessionLocal()
        try:
            query = select(File)
            if package_id:
                query = query.where(File.package_id == package_id)
            return session.execute(query).scalars().all()
        finally:
            session.close()

    def pause_download(self, file_id: int) -> bool:
        """Pause a download."""
        session = SessionLocal()
        try:
            file_record = session.get(File, file_id)
            if file_record and file_record.aria2_gid:
                try:
                    self.aria2.pause(file_record.aria2_gid)
                except Exception as e:
                    logger.warning(f"Failed to pause in aria2: {e}")
                file_record.status = "PAUSED"
                session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error pausing download {file_id}: {e}")
            return False
        finally:
            session.close()

    def resume_download(self, file_id: int) -> bool:
        """Resume a paused download."""
        session = SessionLocal()
        try:
            file_record = session.get(File, file_id)
            if file_record and file_record.aria2_gid:
                try:
                    self.aria2.resume(file_record.aria2_gid)
                except Exception as e:
                    logger.warning(f"Failed to resume in aria2: {e}")
                file_record.status = "DOWNLOADING"
                session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error resuming download {file_id}: {e}")
            return False
        finally:
            session.close()

    def remove_download(self, file_id: int, delete_file: bool = False) -> bool:
        """Remove a download."""
        session = SessionLocal()
        try:
            file_record = session.get(File, file_id)
            if file_record:
                if file_record.aria2_gid:
                    self.aria2.remove(file_record.aria2_gid, force=True)
                file_record.status = "CANCELLED"
                session.commit()
                return True
            return False
        finally:
            session.close()
