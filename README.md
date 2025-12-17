# Fetchr

Multi-host file download library with parallel connections, resume capability, and aria2c integration.

## Features

- Async downloads with aiohttp
- Parallel connections with byte-range requests
- Resume capability for interrupted downloads
- aria2c integration for accelerated downloads
- Multiple host support (Gofile, Pixeldrain, 1fichier, etc.)
- Proxy support
- Health check system for host validation

## Installation

```bash
# Install in editable mode
pip install -e .

# Or install from source
pip install .
```

## Supported Hosts

- pixeldrain.com
- gofile.io
- 1fichier.com
- filedot.to
- ranoz.gg
- krakenfiles.com
- uploadflix.cc/net/com
- desiupload.co
- filemirage.com
- upload.ee
- uploadhive.com
- send.now
- anonfile.de
- axfc.net

## Quick Start

### Basic Download

```python
import asyncio
from fetchr import Downloader

async def main():
    downloader = Downloader()
    
    await downloader.download_file(
        url="https://pixeldrain.com/u/abc123",
        download_dir="./downloads"
    )

asyncio.run(main())
```

### Download with Progress Callback

```python
import asyncio
from fetchr import Downloader

async def progress_callback(downloaded: int, total: int):
    percent = (downloaded / total) * 100 if total > 0 else 0
    print(f"Progress: {percent:.1f}% ({downloaded}/{total} bytes)")

async def main():
    downloader = Downloader(max_concurrent_global=10)
    
    await downloader.download_file(
        url="https://gofile.io/d/abc123",
        download_dir="./downloads",
        callback_progress=progress_callback
    )

asyncio.run(main())
```

### Using Individual Resolvers

```python
import asyncio
from fetchr.hosts.gofile import GofileResolver
from fetchr.hosts.pixeldrain import PixelDrainResolver

async def main():
    # Gofile example
    async with GofileResolver() as resolver:
        info = await resolver.get_download_info("https://gofile.io/d/abc123")
        print(f"Filename: {info.filename}")
        print(f"Size: {info.size} bytes")
        print(f"Direct URL: {info.download_url}")

    # Pixeldrain example
    async with PixelDrainResolver() as resolver:
        info = await resolver.get_download_info("https://pixeldrain.com/u/xyz789")
        print(f"Filename: {info.filename}")

asyncio.run(main())
```

### Batch Downloads

```python
import asyncio
from fetchr import Downloader

async def main():
    downloader = Downloader(max_concurrent_global=5)
    
    urls = [
        "https://pixeldrain.com/u/file1",
        "https://gofile.io/d/file2",
        "https://krakenfiles.com/view/file3",
    ]
    
    tasks = [
        downloader.download_file(url, "./downloads")
        for url in urls
    ]
    
    await asyncio.gather(*tasks)

asyncio.run(main())
```

## Health Checks

Verify that host resolvers are working correctly:

```python
import asyncio
from fetchr.health import HealthChecker

async def main():
    checker = HealthChecker()
    
    # Check a specific host
    result = await checker.check_host("gofile")
    print(f"Gofile status: {'OK' if result.success else 'FAILED'}")
    print(f"Message: {result.message}")
    
    # Check all hosts
    results = await checker.check_all()
    for host, result in results.items():
        status = "OK" if result.success else "FAILED"
        print(f"{host}: {status} - {result.message}")

asyncio.run(main())
```

## Configuration

Create a `proxies.txt` file in the config directory for proxy support:

```
proxy1.example.com:8080
proxy2.example.com:8080
```

# Changelong
- 17/12/25 - Added support for premium acocunts anonfile
envirnment variables:
ANONFILE_USE_PREMIUM
ANONFILE_LOGIN_COOKIE
ANONFILE_XFSS_COOKIE

## Requirements

- Python >= 3.10
- aiohttp
- aiofiles
- aiohttp-socks
- rich
- aria2c (optional, for accelerated downloads)

## License

MIT
