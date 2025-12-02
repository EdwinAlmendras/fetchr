from pathlib import Path

import asyncio
import aiofiles
import os
from typing import Any, Callable
import aiohttp
import time
from fetchr.aria2c import Aria2cDownloader
from rich import print
import logging
logger = logging.getLogger("downloader")

class ParallelDownloader():
    async def _download_parallel(
        self,
        download_info,
        download_dir: Path,
        total_size: int,
        parallel_connections: int,
        session: aiohttp.ClientSession,
        callback_progress: Callable[[int, int], None] = None,
        chunk_size: int = 4 * 1024 * 1024,
        ignore_ssl: bool = False,
        use_random_proxy: bool = False,
        download_with_aria2c: bool = False
    ) -> str:
        """Download file using parallel connections with range requests and resume capability"""
        
        # Calculate segments
        segment_size = total_size // parallel_connections
        segments = []
        
        for i in range(parallel_connections):
            start = i * segment_size
            if i == parallel_connections - 1:  # Last segment gets remaining bytes
                end = total_size - 1
            else:
                end = start + segment_size - 1
            segments.append((i, start, end))
        
        logger.debug(f"Creating {len(segments)} parallel downloads")
        
        # Check existing segments and report detailed status
        segment_status = self._get_segment_status(download_dir, download_info.filename, segments)
        
        if segment_status['complete']:
            logger.debug(f"✅ Found {len(segment_status['complete'])} complete segments: {segment_status['complete']}")
        
        if segment_status['partial']:
            logger.debug(f"🔄 Found {len(segment_status['partial'])} partial segments to resume: {segment_status['partial']}")
        
        if segment_status['missing']:
            logger.debug(f"❌ Missing {len(segment_status['missing'])} segments: {segment_status['missing']}")
        
        if segment_status['corrupted']:
            logger.warning(f"⚠️  Found {len(segment_status['corrupted'])} corrupted segments: {segment_status['corrupted']}")
            # Clean up corrupted segments
            expected_sizes = [end_byte - start_byte + 1 for _, start_byte, end_byte in segments]
            await self._cleanup_corrupted_segments(
                download_dir.joinpath(download_info.filename), 
                len(segments), 
                expected_sizes
            )
        
        # Progress tracking with throttling
        progress_lock = asyncio.Lock()
        segment_progress = {i: 0 for i, _, _ in segments}
        last_progress_update = 0
        progress_update_interval = 1.0  # Update progress every 1 second
        
        # Initialize progress with existing partial files
        initial_total = 0
        for i, (_, start_byte, end_byte) in enumerate(segments):
            segment_path = download_dir.joinpath(f"{download_info.filename}.part{i}")
            if segment_path.exists():
                existing_size = segment_path.stat().st_size
                expected_size = end_byte - start_byte + 1
                if existing_size <= expected_size:
                    segment_progress[i] = existing_size
                    initial_total += existing_size
        
        if initial_total > 0:
            logger.debug(f"📊 Resuming download with {initial_total:,} bytes already downloaded ({initial_total/total_size*100:.1f}%)")
        
        async def update_progress(segment_id: int, downloaded: int):
            nonlocal last_progress_update
            
            if callback_progress:
                async with progress_lock:
                    # Update segment progress
                    segment_progress[segment_id] = downloaded
                    
                    current_time = time.monotonic()
                    
                    # Only update progress if enough time has passed
                    if current_time - last_progress_update >= progress_update_interval:
                        # Calculate total downloaded by checking ALL segment files
                        total_downloaded = 0
                        
                        for i, (_, start_byte, end_byte) in enumerate(segments):
                            segment_path = download_dir.joinpath(f"{download_info.filename}.part{i}")
                            if segment_path.exists():
                                # Always use the actual file size, not the progress tracking
                                actual_size = segment_path.stat().st_size
                                expected_size = end_byte - start_byte + 1
                                
                                # Add the actual downloaded bytes (capped at expected size)
                                total_downloaded += min(actual_size, expected_size)
                                
                                # Update progress tracking to match actual file
                                segment_progress[i] = min(actual_size, expected_size)
                        
                        await callback_progress(total_downloaded, total_size)
                        # Update the last progress time
                        last_progress_update = current_time
        
        async def recalculate_progress():
            """Recalculate progress from actual files when segments fail"""
            if callback_progress:
                async with progress_lock:
                    total_downloaded = 0
                    
                    for i, (_, start_byte, end_byte) in enumerate(segments):
                        segment_path = download_dir.joinpath(f"{download_info.filename}.part{i}")
                        if segment_path.exists():
                            actual_size = segment_path.stat().st_size
                            expected_size = end_byte - start_byte + 1
                            total_downloaded += min(actual_size, expected_size)
                            segment_progress[i] = min(actual_size, expected_size)
                    
                    await callback_progress(total_downloaded, total_size)
        
        # Create download tasks
        tasks = []
        retry_stats = {}  # Track retry statistics
        
        for segment_id, start_byte, end_byte in segments:
            task = asyncio.create_task(
                self._download_segment(
                    download_info=download_info,
                    segment_id=segment_id,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    download_dir=download_dir,
                    session=session,
                    progress_callback=lambda downloaded, sid=segment_id: update_progress(sid, downloaded),
                    chunk_size=chunk_size,
                    ignore_ssl=ignore_ssl,
                    use_random_proxy=use_random_proxy,
                    download_with_aria2c=download_with_aria2c
                )
            )
            tasks.append(task)
        file_path = download_dir.joinpath(download_info.filename)
        try:
            # Wait for all segments to complete, but handle individual failures
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check for failed segments
            failed_segments = []
            successful_segments = []
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    failed_segments.append(i)
                    import traceback
                    traceback.print_exc()
                    exc_str = str(result)
                    logger.error(f"💥 Segment {i} failed completely: {exc_str}")
                else:
                    successful_segments.append(i)
            
            if failed_segments:
                logger.error(f"❌ {len(failed_segments)} segments failed: {failed_segments}")
                logger.debug(f"✅ {len(successful_segments)} segments completed: {successful_segments}")
                
                # Calculate total bytes that would be missing
                missing_bytes = 0
                for segment_id in failed_segments:
                    _, start_byte, end_byte = segments[segment_id]
                    expected_size = end_byte - start_byte + 1
                    missing_bytes += expected_size
                
                logger.error(f"💥 Download incomplete: {missing_bytes:,} bytes missing from {len(failed_segments)} segments")
                logger.error(f"🚫 Cannot assemble file - missing critical segments would result in corrupted file")
                
                # Calculate total progress preserved
                preserved_bytes = 0
                for segment_id in successful_segments:
                    _, start_byte, end_byte = segments[segment_id]
                    expected_size = end_byte - start_byte + 1
                    preserved_bytes += expected_size
                
                logger.debug(f"💾 Preserved {preserved_bytes:,} bytes ({preserved_bytes/total_size*100:.1f}%) for resume")
                logger.debug(f"🔄 You can retry this download - it will resume from where it left off")
                
                # Show which segments are preserved
                logger.debug(f"📋 Segment status:")
                for i, (_, start_byte, end_byte) in enumerate(segments):
                    segment_path = download_dir.joinpath(f"{download_info.filename}.part{i}")
                    if i in successful_segments:
                        if segment_path.exists():
                            actual_size = segment_path.stat().st_size
                            expected_size = end_byte - start_byte + 1
                            if actual_size == expected_size:
                                logger.debug(f"   ✅ Segment {i}: Complete ({actual_size:,} bytes)")
                            else:
                                logger.debug(f"   🔄 Segment {i}: Partial ({actual_size:,}/{expected_size:,} bytes)")
                        else:
                            logger.debug(f"   ❓ Segment {i}: Missing file")
                    else:
                        logger.debug(f"   ❌ Segment {i}: Failed")
                
                # DON'T clean up anything - preserve all segments for resume
                raise Exception(f"Download failed: {len(failed_segments)} segments failed after all retries - but progress preserved for resume")
            
            # All segments successful, assemble final file
            print()  # Clear the progress line
            # Calculate expected segment sizes for validation
            expected_segment_sizes = []
            for _, start_byte, end_byte in segments:
                expected_size = end_byte - start_byte + 1
                expected_segment_sizes.append(expected_size)
            await self._assemble_segments(download_dir, file_path, len(segments), expected_segment_sizes)
            logger.info(f"Download complete: {file_path} ({file_path.stat().st_size} bytes, {len(segments)} segments)")
            return file_path
            
        except Exception as e:
            # Clear the progress line on error
            print()  # Clear the progress line
            # Only cleanup if we're not resuming (i.e., if this is a fresh start)
            # For resume scenarios, we want to keep partial segments
            logger.warning(f"Download failed: {e}")
            logger.debug("Keeping partial segments for potential resume")
            raise e

    async def _download_segment(
        self,
        download_info,
        segment_id: int,
        start_byte: int,
        end_byte: int,
        download_dir: Path,
        session: aiohttp.ClientSession,
        progress_callback: Callable[[int], None],
        chunk_size: int = 4 * 1024 * 1024,
        ignore_ssl: bool = False,
        retries: int = 3,
        use_random_proxy: bool = False,
        download_with_aria2c: bool = False
    ):
        """Download a specific byte range segment with resume capability"""
        
        segment_path = f"{download_dir.joinpath(download_info.filename)}.part{segment_id}"
        segment_size = end_byte - start_byte + 1
        
        # Función helper para recalcular el punto de inicio
        def get_current_start():
            if Path(segment_path).exists():
                existing_size = Path(segment_path).stat().st_size
                if existing_size == segment_size:
                    return None  # Ya está completo
                elif existing_size < segment_size:
                    return start_byte + existing_size
                else:
                    # Archivo corrupto/oversized
                    if existing_size > segment_size * 1.1:
                        Path(segment_path).unlink()  # Eliminar y empezar de nuevo
                        return start_byte
                    else:
                        return None  # Tratarlo como completo
            else:
                return start_byte
        
        # Verificación inicial
        initial_start = get_current_start()
        if initial_start is None:
            logger.debug(f"✅ Segment {segment_id} already complete")
            return segment_path
        
        return await self._download_segment_with_retry(
            download_info, segment_id, start_byte, end_byte, 
            download_dir, session, progress_callback, chunk_size, 
            ignore_ssl, retries, use_random_proxy, segment_path, 
            get_current_start, download_with_aria2c, 
            segment_size
        )
            
    
    async def _download_segment_with_retry(
            self, download_info, segment_id, 
            start_byte, end_byte, download_dir, 
            session, progress_callback, chunk_size, 
            ignore_ssl, retries, use_random_proxy, 
            segment_path, get_current_start, download_with_aria2c, 
            segment_size
    ):
        
        if download_with_aria2c:
            return await self._download_segment_with_aria2c(
                download_info, segment_id, end_byte, use_random_proxy, 
                segment_path, get_current_start, ignore_ssl
            )
        else:
            return await self._download_segment_with_aiohttp(
                download_info, segment_id, 
                start_byte, end_byte,
                session, progress_callback, 
                chunk_size, ignore_ssl, retries, use_random_proxy, 
                segment_path, get_current_start, segment_size
            )
            
    async def _download_segment_with_aria2c(
            self, download_info, segment_id,
            end_byte, use_random_proxy, 
            segment_path, get_current_start, ignore_ssl
    ):
        
        current_start = get_current_start()
        if current_start is None:
            logger.debug(f"✅ Segment {segment_id} completed during retry")
            return segment_path
        
        headers = download_info.headers.copy() if download_info.headers else {}
        headers['Range'] = f'bytes={current_start}-{end_byte}'
        cmd = Aria2cDownloader.create_command(
            download_info.download_url,
            segment_path,
            headers,
            ignore_ssl=ignore_ssl,
            use_random_proxy=use_random_proxy,
        )
        print(f"Running command: {' '.join(cmd)}")
        process = await asyncio.create_subprocess_exec(
            *cmd,
        )
        await process.wait()
        if process.returncode == 0:
            logger.info(f"✅ Segment {segment_id} completed")
            return segment_path
        else:
            logger.info(f"❌ Segment {segment_id} failed")
            raise Exception(f"Segment {segment_id} failed")
        
    async def _download_segment_with_aiohttp(
            self, download_info, segment_id, 
            start_byte, end_byte,session, progress_callback, 
            chunk_size, ignore_ssl, retries, use_random_proxy, 
            segment_path, get_current_start, segment_size
    ):
        for attempt in range(retries + 1):
            try:
                # RECALCULAR current_start en cada intento
                current_start = get_current_start()
                
                if current_start is None:
                    logger.debug(f"✅ Segment {segment_id} completed during retry")
                    return segment_path
                
                # Determinar si estamos resumiendo o empezando
                is_resuming = current_start > start_byte
                remaining_bytes = end_byte - current_start + 1
                
                # Preparar headers con range request
                headers = download_info.headers.copy() if download_info.headers else {}
                headers['Range'] = f'bytes={current_start}-{end_byte}'
                
                # Logging apropiado
                if attempt == 0:
                    if is_resuming:
                        existing_size = current_start - start_byte
                        logger.info(f"🔄 Segment {segment_id}: resuming from {existing_size:,}/{segment_size:,} bytes")
                    else:
                        logger.debug(f"📥 Segment {segment_id}: starting download ({remaining_bytes:,} bytes)")
                else:
                    logger.debug(f"🔄 Segment {segment_id}: retry {attempt}/{retries} from position {current_start - start_byte:,}/{segment_size:,}")
                
                
                logger.debug(f"Downloading segment {segment_id} from {download_info.download_url} with headers: {headers}")
                
                async with session.get(
                    download_info.download_url,
                    headers=headers,
                    ssl=False if ignore_ssl else True,
                    #timeout=timeout
                ) as response:
                    
                    response.raise_for_status()
                    
                    if response.status != 206:
                        raise Exception(f"Server doesn't support range requests. Status: {response.status}")
                    
                    # SIEMPRE usar modo append - el current_start ya está calculado correctamente
                    async with aiofiles.open(segment_path, 'ab') as f:
                        downloaded = 0
                        last_callback = 0
                        callback_interval = 2.0
                        
                        async for chunk in response.content.iter_chunked(chunk_size):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            now = time.monotonic()
                            if progress_callback and now - last_callback >= callback_interval:
                                # El callback recibe el total descargado por este segmento
                                total_segment_downloaded = (current_start - start_byte) + downloaded
                                await progress_callback(total_segment_downloaded)
                                last_callback = now
                    
                    # Verificar que el segmento se completó
                    expected_downloaded = end_byte - current_start + 1
                    if downloaded != expected_downloaded:
                        raise Exception(f"Segment {segment_id} incomplete: {downloaded}/{expected_downloaded}")
                    
                    logger.debug(f"✅ Segment {segment_id} completed: {downloaded} bytes added")
                    return segment_path
                    
            except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
                import traceback
                error_type = type(e).__name__
                logger.debug(f"❌ Segment {segment_id} attempt {attempt + 1} failed ({error_type}): {e}")
                if attempt == retries:
                    logger.debug(f"💥 Segment {segment_id} failed after {retries + 1} attempts - preserving partial data")
                    if Path(segment_path).exists():
                        partial_size = Path(segment_path).stat().st_size
                        logger.debug(f"💾 Preserved partial segment {segment_id} ({partial_size:,} bytes)")
                    raise
                else:
                    wait_time = 2 ** attempt
                    logger.debug(f"⏳ Segment {segment_id} waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
    
    
    
    async def _assemble_segments(self, folder_path: Path, file_path: Path, segment_count: int, expected_segment_sizes: list = None):
        """Assemble all segment files into final file with integrity validation"""
        
        logger.debug(f"🔍 Validating {segment_count} segments before assembly...")
        
        # Validate all segments exist and have correct sizes
        total_size = 0
        for i in range(segment_count):
            segment_path = file_path.with_name(f"{file_path.name}.part{i}")
            
            if not segment_path.exists():
                raise Exception(f"Missing segment file: {segment_path}")
            
            # Check segment size if expected sizes provided
            if expected_segment_sizes:
                actual_size = segment_path.stat().st_size
                expected_size = expected_segment_sizes[i]
                if actual_size != expected_size:
                    raise Exception(f"Segment {i} size mismatch: expected {expected_size:,} bytes, got {actual_size:,} bytes")
            
            total_size += segment_path.stat().st_size
            logger.debug(f"✅ Segment {i} validated: {segment_path.stat().st_size:,} bytes")
        
        logger.debug(f"✅ All segments validated. Total size: {total_size:,} bytes")
        
        # Assemble the file
        async with aiofiles.open(file_path, 'wb') as final_file:
            for i in range(segment_count):
                segment_path = file_path.with_name(f"{file_path.name}.part{i}")
                
                async with aiofiles.open(segment_path, 'rb') as segment_file:
                    while True:
                        chunk = await segment_file.read(8192)
                        if not chunk:
                            break
                        await final_file.write(chunk)
                
                # Remove segment file after copying
                os.remove(segment_path)
                logger.debug(f"✅ Assembled segment {i}")
        
        # Verify final file size
        final_size = file_path.stat().st_size
        if final_size != total_size:
            raise Exception(f"Final file size mismatch: expected {total_size:,} bytes, got {final_size:,} bytes")
        
        logger.debug(f"✅ File assembly completed successfully: {final_size:,} bytes")
        
        # Additional integrity check
        if expected_segment_sizes:
            expected_total = sum(expected_segment_sizes)
            if final_size != expected_total:
                raise Exception(f"Integrity check failed: expected {expected_total:,} bytes, got {final_size:,} bytes")
            logger.debug(f"✅ Integrity check passed: {final_size:,} bytes")

    async def _cleanup_segments(self, file_path: Path, segment_count: int):
        """Clean up partial segment files on error"""
        
        for i in range(segment_count):
            segment_path = file_path.with_name(f"{file_path.name}.part{i}")
            if segment_path.exists():
                try:
                    segment_path.unlink()
                    logger.debug(f"Cleaned up segment {i}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {segment_path}: {e}")

    async def _cleanup_corrupted_segments(self, file_path: Path, segment_count: int, expected_segment_sizes: list):
        """Clean up only corrupted or incomplete segment files"""
        
        cleaned_count = 0
        for i in range(segment_count):
            segment_path = file_path.with_name(f"{file_path.name}.part{i}")
            if segment_path.exists():
                try:
                    actual_size = segment_path.stat().st_size
                    expected_size = expected_segment_sizes[i]
                    
                    if actual_size != expected_size:
                        segment_path.unlink()
                        logger.debug(f"Cleaned up corrupted segment {i} (size: {actual_size}, expected: {expected_size})")
                        cleaned_count += 1
                    else:
                        logger.debug(f"Segment {i} is intact ({actual_size} bytes)")
                        
                except Exception as e:
                    logger.warning(f"Failed to cleanup {segment_path}: {e}")
        
        logger.debug(f"Cleaned up {cleaned_count} corrupted segments")
        return cleaned_count

    def _verify_segment_integrity(self, segment_path: Path, expected_size: int) -> bool:
        """Verify if a segment file is complete and not corrupted"""
        try:
            if not segment_path.exists():
                return False
            
            actual_size = segment_path.stat().st_size
            return actual_size == expected_size
            
        except Exception as e:
            logger.warning(f"Error verifying segment {segment_path}: {e}")
            return False

    def _get_segment_status(self, download_dir: Path, filename: str, segments: list) -> dict:
        """Get status of all segments (complete, partial, missing)"""
        status = {
            'complete': [],
            'partial': [],
            'missing': [],
            'corrupted': []
        }
        
        for segment_id, start_byte, end_byte in segments:
            segment_path = download_dir.joinpath(f"{filename}.part{segment_id}")
            expected_size = end_byte - start_byte + 1
            
            if segment_path.exists():
                try:
                    actual_size = segment_path.stat().st_size
                    if actual_size == expected_size:
                        status['complete'].append(segment_id)
                    elif actual_size < expected_size:
                        status['partial'].append(segment_id)
                    else:
                        status['corrupted'].append(segment_id)
                except Exception as e:
                    logger.warning(f"Error checking segment {segment_id}: {e}")
                    status['corrupted'].append(segment_id)
            else:
                status['missing'].append(segment_id)
        
        return status

    async def _validate_connection(self, session: aiohttp.ClientSession, url: str, ignore_ssl: bool = False) -> bool:
        """Validate connection to the server before attempting download"""
        try:
            timeout = aiohttp.ClientTimeout(total=10, connect=5)  # Quick validation
            async with session.head(url, ssl=False if ignore_ssl else True, timeout=timeout) as response:
                return response.status < 500  # Server errors indicate connection issues
        except Exception as e:
            logger.debug(f"Connection validation failed: {e}")
            return False

    async def _cleanup_failed_download(self, download_dir: Path, filename: str, segment_count: int):
        """Clean up all partial files when download completely fails"""
        logger.debug(f"🧹 Cleaning up failed download: {filename}")
        cleaned_count = 0
        
        for i in range(segment_count):
            segment_path = download_dir.joinpath(f"{filename}.part{i}")
            if segment_path.exists():
                try:
                    segment_path.unlink()
                    cleaned_count += 1
                    logger.debug(f"Cleaned up segment {i}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup segment {i}: {e}")
        
        logger.debug(f"🧹 Cleaned up {cleaned_count} partial segments from failed download")
        return cleaned_count
