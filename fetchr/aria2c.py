from pathlib import Path
import asyncio
import aiofiles
import os
from typing import Optional
from fetchr.network import get_random_proxy
from fetchr.types import DownloadInfo

class Aria2cDownloader():
    async def download_with_multithread(
        self,
        download_info: DownloadInfo,
        output_path: Path,
        ignore_ssl: bool = False,
        use_connections: int = 1,
        use_concurrent_downloads: int = 1,
        max_connections: int = 1,
        use_random_proxy: bool = False
    ) -> Optional[str]:
        size_part = download_info.size // use_connections
        tasks = []
        
        for i in range(use_connections):
            start_byte = i * size_part
            end_byte = start_byte + size_part - 1
            
            headers = {
                "Range": f"bytes={start_byte}-{end_byte}"
            }
            
            part_path = output_path.with_suffix(f".aria2c.part{i}")
            
            task = asyncio.create_task(self.download(
                download_info, 
                part_path, 
                headers,
                ignore_ssl, 
                use_random_proxy=use_random_proxy
            ))
            tasks.append(task)
        # Wait for all tasks to complete
        results = await asyncio.gather(*[task for task, _ in tasks], return_exceptions=True)
        
        # Check for errors and retry if needed
        failed_tasks = []
        import traceback
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"❌ Part {i} failed: {result}")
                traceback.print_exception(type(result), result, result.__traceback__)
                failed_tasks.append(tasks[i][1])  # Get the function to retry
        if failed_tasks:
            print("🔄 Retrying failed parts...")
            retry_tasks = [asyncio.create_task(func()) for func in failed_tasks]
            await asyncio.gather(*retry_tasks, return_exceptions=True)
        
        # Assemble all parts into final file
        await self._assemble_parts(output_path, use_connections, download_info.size)
        
        return output_path

    async def download(
        self,
        download_info: DownloadInfo,
        output_path: Path,
        headers: dict = {},
        ignore_ssl: bool = False,
        use_connections: int = 5,
        max_connections: int = 1,
        max_concurrent_downloads: int = 5,
        use_random_proxy: bool = False,
        proxy: str = None,
        silent: bool = False,
    ) -> Optional[str]:
        cmd = Aria2cDownloader.create_command(
            url=download_info.download_url,
            output_path=output_path,
            headers=headers,
            max_connections=max_connections,
            max_concurrent_downloads=max_concurrent_downloads,
            use_connections=use_connections,
            use_random_proxy=use_random_proxy,
            ignore_ssl=ignore_ssl,
            silent=silent,
            proxy=proxy,
            download_info=download_info,
        )
        print(f"cmd: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
        )
        
        await process.wait()
        if process.returncode == 0:
            return str(output_path)
        else:
            print("❌ Error in the download")
            raise Exception("Error in the download")
    
    @staticmethod
    def create_command(
        url: str,
        output_path: Path,
        headers: dict = {},
        max_connections: int = 1,
        max_concurrent_downloads: int = 5,
        use_connections: int = 5,
        use_random_proxy: bool = False,
        proxy: str = None,
        ignore_ssl: bool = False,
        silent: bool = False,
        download_info: DownloadInfo = None,
    ):
        cmd = [
            "aria2c",
            url,
            "-c",
            "-d", str(output_path.parent),
            f"-x", str(max_connections), # max connections
            f"-s", str(use_connections), # splited parts
            #f"-j", str(max_concurrent_downloads), # max concurrent downloads
            "-o", str(download_info.filename),
        ]

        if headers:
            for key, value in headers.items():
                cmd.extend(["--header", f"{key}: {value}"])

        if use_random_proxy:
            proxy = get_random_proxy()
            if proxy:
                cmd.extend(["--all-proxy", proxy])
        elif proxy:
            cmd.extend(["--all-proxy", proxy])
        if ignore_ssl:
            cmd.append("--check-certificate=false")
        if silent:
            cmd.append("--quiet")
        return cmd
    
    async def _assemble_parts(self, output_path: Path, part_count: int, expected_total_size: int = None):
        """Assemble all part files into final file with size validation"""
        print(f"🔧 Assembling {part_count} parts into final file...")
        
        # Validate all parts exist and calculate total size
        total_size = 0
        for i in range(part_count):
            part_path = output_path.with_suffix(f".aria2c.part{i}")
            if not part_path.exists():
                raise Exception(f"Missing part file: {part_path}")
            
            part_size = part_path.stat().st_size
            total_size += part_size
            print(f"📁 Part {i}: {part_size:,} bytes")
        
        # Validate total size if expected size provided
        if expected_total_size and total_size != expected_total_size:
            raise Exception(f"Size mismatch: expected {expected_total_size:,} bytes, got {total_size:,} bytes")
        
        print(f"📊 Total size: {total_size:,} bytes")
        
        # Assemble the file
        async with aiofiles.open(output_path, 'wb') as final_file:
            for i in range(part_count):
                part_path = output_path.with_suffix(f".part{i}")
                
                async with aiofiles.open(part_path, 'rb') as part_file:
                    while True:
                        chunk = await part_file.read(8192)
                        if not chunk:
                            break
                        await final_file.write(chunk)
                
                # Remove part file after copying
                os.remove(part_path)
                print(f"✅ Assembled part {i}")
        
        # Verify final file size
        final_size = output_path.stat().st_size
        if final_size != total_size:
            raise Exception(f"Final file size mismatch: expected {total_size:,} bytes, got {final_size:,} bytes")
        
        print(f"✅ Final file assembled: {output_path} ({final_size:,} bytes)")
