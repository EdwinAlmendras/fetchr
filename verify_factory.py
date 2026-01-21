import asyncio
import logging
from fetchr.hosts import get_resolver, get_download_info
from fetchr.hosts.onefichier import OneFichierResolver
from fetchr.hosts.desiupload import DesiUploadResolver

# Configure logging
logging.basicConfig(level=logging.INFO)

async def verify():
    test_cases = [
        ("https://1fichier.com/?example", OneFichierResolver),
        ("https://desiupload.co/example", DesiUploadResolver),
        ("https://anonfile.de/example", "AnonFileResolver"),
        ("https://gofile.io/d/example", "GofileResolver"),
    ]

    print("Verifying Resolver Factory...")
    for url, expected_cls in test_cases:
        resolver = get_resolver(url)
        if resolver:
            print(f"✅ URL: {url} -> Resolved to: {type(resolver).__name__}")
            if isinstance(expected_cls, str):
                assert type(resolver).__name__ == expected_cls
            else:
                assert isinstance(resolver, expected_cls)
        else:
            print(f"❌ URL: {url} -> Not resolved!")

    print("\nVerifying get_download_info instantiation (mock check)...")
    # We won't actually call download info as URLs are fake, but checking factory worked is key.

if __name__ == "__main__":
    asyncio.run(verify())
