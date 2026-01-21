import aiohttp
import asyncio
import logging
from bs4 import BeautifulSoup
from typing import Dict
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
from fetchr.network import get_aiohttp_proxy_connector, get_random_proxy
from fetchr.captcha import solve_css_position_captcha

logger = logging.getLogger("fetchr.hosts.exload")

EXLOAD_COUNTDOWN_SECONDS = 60


class ExloadResolver(AbstractHostResolver):
    host = "ex-load.com"
    def __init__(self, timeout: int = 120, skip_countdown: bool = False, max_retries: int = 5):
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.skip_countdown = skip_countdown
        self.max_retries = max_retries
        self.proxy = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        self.session = None

    async def __aenter__(self):
        logger.debug("Initializing ExloadResolver session")
        self.proxy = get_random_proxy()
        connector = aiohttp.TCPConnector()
        if self.proxy:
            logger.debug(f"Using proxy: {self.proxy}")
            self.session = aiohttp.ClientSession(connector=connector, proxy=self.proxy)
        else:
            logger.debug("No proxy available, using direct connection")
            self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            logger.debug("Closing ExloadResolver session")
            await self.session.close()

    def _extract_download_form_data(self, soup: BeautifulSoup) -> Dict[str, str]:
        form = soup.find('form', attrs={'name': 'F1'})
        if not form:
            form = soup.find('input', attrs={'name': 'op', 'value': 'download2'})
            if form:
                form = form.find_parent('form')
        
        if not form:
            raise ValueError("Download form (F1/download2) not found")

        form_data = {}
        for input_tag in form.find_all('input'):
            name = input_tag.get('name')
            value = input_tag.get('value', '')
            if name:
                form_data[name] = value
        
        logger.debug(f"Extracted download form data: {form_data}")
        return form_data

    async def get_download_info(self, url: str) -> DownloadInfo:
        if not self.session:
            raise RuntimeError("Use within context manager: async with ExloadResolver() as resolver:")

        logger.info(f"[STEP 1] Processing URL: {url}")

        logger.debug(f"[STEP 1] Sending GET request to: {url}")
        response = await self.session.get(url, headers=self.headers)
        logger.debug(f"[STEP 1] Response status: {response.status}")
        response.raise_for_status()
        html_content = await response.text()
        logger.debug(f"[STEP 1] Received HTML length: {len(html_content)} bytes")
        soup = BeautifulSoup(html_content, 'html.parser')

        logger.debug("[STEP 2] Looking for captcha div...")
        captcha_div = soup.select_one("#countover1 table tr td div")
        if captcha_div:
            logger.debug("[STEP 2] Found captcha div with selector: #countover1 table tr td div")
        else:
            captcha_div = soup.select_one("table tr td div[style*='background:#ccc']")
            if captcha_div:
                logger.debug("[STEP 2] Found captcha div with selector: table tr td div[style*='background:#ccc']")
        
        if not captcha_div:
            logger.error("[STEP 2] Captcha div not found! Saving HTML for debug...")
            with open("exload_debug.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.error("[STEP 2] HTML saved to exload_debug.html")
            raise ValueError("Captcha div not found")

        logger.debug(f"[STEP 2] Captcha div HTML: {captcha_div}")

        form_data = self._extract_download_form_data(soup)
        form_data['adblock_detected'] = '0'
        captcha_code = solve_css_position_captcha(captcha_div)
        logger.info(f"[STEP 2] Solved captcha code: {captcha_code}")
        form_data['code'] = captcha_code
        logger.debug(f"[STEP 2] Form data for POST: {form_data}")

        if self.skip_countdown:
            logger.warning(f"[STEP 3] SKIPPING countdown (skip_countdown=True)")
        else:
            logger.info(f"[STEP 3] Waiting {EXLOAD_COUNTDOWN_SECONDS} seconds...")
            await asyncio.sleep(EXLOAD_COUNTDOWN_SECONDS)
            logger.debug("[STEP 3] Countdown finished")

        logger.info("[STEP 4] Submitting form with captcha")
        async with self.session.post(url, data=form_data, headers=self.headers, allow_redirects=False) as response:
            logger.debug(f"[STEP 4] Response status: {response.status}")
            logger.debug(f"[STEP 4] Response headers: {dict(response.headers)}")
            
            if response.status in (301, 302, 303, 307, 308):
                direct_url = response.headers.get('Location')
                logger.info(f"[STEP 4] Redirect detected to: {direct_url}")
                if direct_url:
                    filename = direct_url.split("/")[-1]
                    logger.info(f"[STEP 5] Filename: {filename}")
                    
                    logger.debug(f"[STEP 6] Sending HEAD request with up to {self.max_retries} retries...")
                    filesize = 0
                    for attempt in range(self.max_retries):
                        async with self.session.head(direct_url, ssl=False, headers=self.headers) as head_response:
                            logger.debug(f"[STEP 6] Attempt {attempt + 1}/{self.max_retries}: HEAD response status: {head_response.status}")
                            if head_response.status == 200:
                                if 'Content-Length' in head_response.headers:
                                    filesize = int(head_response.headers['Content-Length'])
                                    logger.info(f"[STEP 6] File size: {filesize} bytes ({filesize / 1024 / 1024:.2f} MB)")
                                else:
                                    logger.warning("[STEP 6] Content-Length header not found")
                                break
                            elif head_response.status == 404:
                                logger.warning(f"[STEP 6] 404 on attempt {attempt + 1}, retrying...")
                                await asyncio.sleep(0.5)
                            else:
                                logger.warning(f"[STEP 6] Unexpected status {head_response.status}")
                                break
                    else:
                        logger.warning(f"[STEP 6] All {self.max_retries} retries exhausted, proceeding with filesize=0")
                    
                    logger.info("[DONE] Successfully resolved download info via redirect")
                    return DownloadInfo(
                        filename=filename,
                        size=filesize,
                        download_url=direct_url,
                        headers={},
                    )
            
            response.raise_for_status()
            html_content = await asyncio.wait_for(response.text(), timeout=30)
            logger.debug(f"[STEP 4] Received HTML length: {len(html_content)} bytes")
            soup = BeautifulSoup(html_content, 'html.parser')

        logger.debug("[STEP 5] Looking for direct download link...")
        anchor = soup.select_one("table a[href*='://']")
        if anchor:
            logger.debug("[STEP 5] Found anchor with selector: table a[href*='://']")
        else:
            anchor = soup.select_one("#direct_link a")
            if anchor:
                logger.debug("[STEP 5] Found anchor with selector: #direct_link a")
            else:
                anchor = soup.select_one("a.downloadbtn")
                if anchor:
                    logger.debug("[STEP 5] Found anchor with selector: a.downloadbtn")
        
        if not anchor:
            logger.error("[STEP 5] Direct download link not found! Saving HTML for debug...")
            with open("exload_final_debug.html", "w", encoding="utf-8") as f:
                f.write(html_content)
            logger.error("[STEP 5] HTML saved to exload_final_debug.html")
            raise ValueError("Direct download link not found")

        direct_url = anchor.get("href")
        filename = direct_url.split("/")[-1]
        logger.info(f"[STEP 5] Direct URL: {direct_url}")
        logger.info(f"[STEP 5] Filename: {filename}")

        logger.debug("[STEP 6] Sending HEAD request to get file size...")
        async with self.session.head(direct_url, ssl=False, headers=self.headers) as response:
            logger.debug(f"[STEP 6] HEAD response status: {response.status}")
            logger.debug(f"[STEP 6] HEAD response headers: {dict(response.headers)}")
            if 'Content-Length' not in response.headers:
                raise ValueError("Content-Length header not found")
            filesize = int(response.headers['Content-Length'])
            logger.info(f"[STEP 6] File size: {filesize} bytes ({filesize / 1024 / 1024:.2f} MB)")

        logger.info("[DONE] Successfully resolved download info")
        return DownloadInfo(
            filename=filename,
            size=filesize,
            download_url=direct_url,
            headers={},
        )
