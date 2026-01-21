import importlib
import pkgutil
from typing import Optional, List, Type
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import logging

logger = logging.getLogger(__name__)

# List to hold registered resolver classes
RESOLVERS: List[Type[AbstractHostResolver]] = []

def _discover_resolvers():
    """
    Dynamically discover and register resolver classes from the current package.
    """
    global RESOLVERS
    if RESOLVERS:
        return

    package_name = __name__
    package_path = __path__

    for _, name, _ in pkgutil.iter_modules(package_path):
        try:
            full_module_name = f"{package_name}.{name}"
            module = importlib.import_module(full_module_name)
            
            for attribute_name in dir(module):
                attribute = getattr(module, attribute_name)
                
                if (isinstance(attribute, type) and 
                    issubclass(attribute, AbstractHostResolver) and 
                    attribute is not AbstractHostResolver and
                    attribute.__module__ == full_module_name): # Avoid importing base classes re-exported
                    
                    RESOLVERS.append(attribute)
                    logger.debug(f"Registered resolver: {attribute.__name__}")
        except Exception as e:
            logger.warning(f"Failed to load module {name}: {e}")

def get_resolver(url: str) -> Optional[AbstractHostResolver]:
    """
    Factory function to get the appropriate resolver for a given URL.
    """
    _discover_resolvers()
    
    for resolver_cls in RESOLVERS:
        try:
            if resolver_cls.match(url):
                return resolver_cls()
        except NotImplementedError:
             logger.warning(f"Resolver {resolver_cls.__name__} does not implement match()")
        except Exception as e:
             logger.error(f"Error checking match for {resolver_cls.__name__}: {e}")
            
    return None

async def get_download_info(url: str) -> DownloadInfo:
    """
    High-level function to get download info for a URL using the appropriate resolver.
    """
    resolver = get_resolver(url)
    if not resolver:
        raise ValueError(f"No resolver found for URL: {url}")
        
    async with resolver as active_resolver:
        return await active_resolver.get_download_info(url)
