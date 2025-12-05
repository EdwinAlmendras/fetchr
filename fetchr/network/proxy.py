"""
Proxy utilities for fetchr
"""
import os
import random
import time
import aiohttp
from fetchr.config import PROXIES_PATH


def get_proxies():
    """Get list of proxies from file. Returns empty list if file doesn't exist."""
    if not PROXIES_PATH.exists():
        print(f"No proxies file found at {PROXIES_PATH}")
        return []
    
    with open(PROXIES_PATH, "r", encoding='utf-8') as f:
        proxies = f.readlines()
    
    fix_proxies = []
    for proxy in proxies:
        proxy = proxy.strip()
        if proxy:
            fix_proxies.append("http://" + proxy)
        
    return fix_proxies


def get_random_proxy():
    """Get a random proxy from the list. Returns None if no proxies available."""
    proxies = get_proxies()
    if not proxies:
        return None
    
    random.seed(time.time())
    return random.choice(proxies)


def get_aiohttp_proxy_connector():
    """Get aiohttp session with optional proxy. Returns session without proxy if none available."""
    proxy_url = get_random_proxy()
    connector = aiohttp.TCPConnector()
    
    if proxy_url:
        session = aiohttp.ClientSession(
            connector=connector,
            proxy=proxy_url
        )
    else:
        session = aiohttp.ClientSession(
            connector=connector
        )
    return session
