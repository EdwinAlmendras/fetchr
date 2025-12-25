import aria2p
import logging
import asyncio
from typing import List, Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

class Aria2DaemonManager:
    """
    Manages the Aria2c daemon process and JSON-RPC connection using aria2p.
    """
    def __init__(self, host="http://127.0.0.1", port=6800, secret="", download_dir: Path = None):
        self.host = host
        self.port = port
        self.secret = secret
        self.api: Optional[aria2p.API] = None
        self.download_dir = download_dir

    async def initialize(self):
        """
        Initialize the connection to Aria2c. 
        Tries to connect to an existing daemon, or starts a new one if not found.
        """
        try:
            # Try connecting first
            self.api = aria2p.API(
                aria2p.Client(
                    host=self.host,
                    port=self.port,
                    secret=self.secret
                )
            )
            self.api.get_global_options()
            logger.info("✅ Connected to existing Aria2c daemon")
        except Exception:
            logger.info("⚠️ Aria2c daemon not found. Starting new instance...")
            # If connection fails, try to start a new instance
            # Note: aria2c must be in PATH
            cmd = [
                "aria2c",
                "--enable-rpc",
                f"--rpc-listen-port={self.port}",
                "--rpc-allow-origin-all",
                "--interface=127.0.0.1",
                f"--dir={str(self.download_dir.resolve())}" if self.download_dir else "",
                # Remove --daemon so we can control the process via asyncio
                # "--daemon=true" 
            ]
            if self.secret:
                cmd.append(f"--rpc-secret={self.secret}")
            
            logger.info(f"Starting aria2c: {' '.join(cmd)}")
            
            # Start process without waiting for it to finish
            try:
                # Open log file for debugging
                log_file = open("aria2_std.log", "w")
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log_file,
                    stderr=log_file
                )
                self._proc = proc # Keep reference
                self._log_file = log_file
            except Exception as e:
                logger.error(f"Failed to launch aria2c: {e}")
                raise

            # Allow some time for startup
            await asyncio.sleep(3)
            
            # Retry connection
            self.api = aria2p.API(
                aria2p.Client(
                    host=self.host,
                    port=self.port,
                    secret=self.secret
                )
            )
            logger.info("✅ Started and connected to new Aria2c daemon")

    def add_download(self, url: str, options: dict = None) -> str:
        """
        Add a download to aria2c. Returns the GID.
        """
        if not self.api:
            raise RuntimeError("Aria2 API not initialized. Call initialize() first.")
        
        downloads = self.api.add(url, options=options)
        return downloads[0].gid

    def get_status(self, gid: str):
        if not self.api:
            return None
        try:
            return self.api.get_download(gid)
        except Exception:
            return None
    
    def pause(self, gid: str):
        if self.api:
            self.api.get_download(gid).pause()
            
    def resume(self, gid: str):
        if self.api:
            self.api.get_download(gid).unpause()

    def remove(self, gid: str, force=False):
        if self.api:
            d = self.api.get_download(gid)
            d.remove(force=force)

    def listen_to_notifications(self, on_change: Callable):
        """
        Attach a callback to aria2 events.
        Note: aria2p supports callbacks but implementing a listening loop 
        might be better handled by a polling task in the main manager 
        or using aria2p's blocking listen().
        """
        # For async applications, better to poll or use a separate thread for listening
        pass
