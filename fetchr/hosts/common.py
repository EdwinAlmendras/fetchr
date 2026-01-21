from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import asyncio
import aiohttp
from bs4 import BeautifulSoup, Tag
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
from ..network import get_aiohttp_proxy_connector

class BaseFormHostResolver(AbstractHostResolver):
    """
    Base class for host resolvers that interact with form-based download sites.
    Provides common functionality for session management, form data extraction,
    and standard headers.
    """

    def __init__(self, timeout: int = 30):
        self.timeout_val = timeout
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

    async def __aenter__(self):
        # Prefer the proxy connector if available/configured, otherwise use standard.
        # Note: Original filedot used get_aiohttp_proxy_connector(), 
        # desiupload used standard ClientSession.
        # We will default to get_aiohttp_proxy_connector() as it likely handles
        # standard connection if no proxy is set, or we can fallback.
        # Assuming get_aiohttp_proxy_connector returns a Session object based on previous usage in filedot.py
        self.session = get_aiohttp_proxy_connector()
        if self.session and self.headers:
            self.session._default_headers.update(self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _extract_form_data(self, soup: BeautifulSoup, form_selector: str = 'form') -> Dict[str, str]:
        """Extract hidden form data from the page."""
        form = soup.select_one(form_selector)
        if not form:
            raise ValueError(f"No form found with selector: {form_selector}")
        
        form_data = {}
        for input_tag in form.find_all('input', type='hidden'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
        
        return form_data

    async def _get_soup(self, url: str, method: str = 'GET', **kwargs) -> BeautifulSoup:
        """Helper to request a page and return BeautifulSoup object."""
        if not self.session:
             raise RuntimeError("Session not initialized. Use 'async with' context manager.")
             
        async with self.session.request(method, url, **kwargs) as response:
            if response.status != 200:
                 raise ValueError(f"Failed to fetch {url}: Status {response.status}")
            html = await response.text()
            return BeautifulSoup(html, 'html.parser')
