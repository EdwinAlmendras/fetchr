import aiohttp
from ..types import DownloadInfo
from ..host_resolver import AbstractHostResolver
import logging
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Callable, Awaitable
import asyncio
import os
import aiofiles
from pathlib import Path
import random
from fetchr.config import CAPTCHAS_DIR

def generate_random_id(length: int = 10):
    chars = "abcdefghijklmnopqrstuvwxyz"
    return "".join(random.choices(chars, k=length))


logger = logging.getLogger("downloader.axfc")


class ErrorImageInvalid(Exception):
    """Exception raised when image is invalid"""
    pass

async def captcha_solver(session: aiohttp.ClientSession, captcha_url: str) -> str:
    id = generate_random_id()
    image_path = Path(f"{CAPTCHAS_DIR}/{id}.jpg")
    text_path = Path(f"{CAPTCHAS_DIR}/{id}.txt")
    async with session.get(captcha_url) as response:
        image_content_types = ["image/jpeg", "image/png", "image/webp"]
        if response.headers.get("Content-Type") not in image_content_types:
            raise ErrorImageInvalid(f"Content-Type is not image/jpeg {response.headers.get('Content-Type')}")
        async with aiofiles.open(image_path, "wb") as f:
            image = await response.read()
            # check if image is not empty
            if not image:
                raise ErrorImageInvalid("No image found")
            await f.write(image)
    code = None
    while not code:
        if text_path.exists():
            async with aiofiles.open(text_path, "r") as f:
                text = await f.read()
                code = text.strip()
        await asyncio.sleep(1)
    image_path.unlink()
    text_path.unlink()
    return code

class AxfcResolver(AbstractHostResolver):
    async def __aenter__(self):
        print("Entering AxfcResolver")
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("Exiting AxfcResolver")
        if self.session:
            await self.session.close()
            
    async def get_download_info(self, url: str) -> DownloadInfo:
        print(f"Processing {url}")
        print(self.session)
        response = await self.session.get(url)
        response.raise_for_status()
        print(response)
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        
        # GET BASIC INFO
        filename = soup.select_one(".comme p").text
        # GET ALL FORM INPUT NAME AND VALUE
        form_data = {}
        for input_tag in soup.find_all("input"):
            name = input_tag.get("name")
            value = input_tag.get("value")
            if name:
                form_data[name] = value
        
        # GET CAPTCHA
        
        captcha = soup.select_one("img")
        base_url = "https://" + urlparse(url).netloc
        
        if captcha:
            captcha_endpoint_url = captcha.get("src")
            captcha_url = base_url + captcha_endpoint_url
            captcha_code = await captcha_solver(self.session, captcha_url)
            form_data["cpt"] = captcha_code
        response = await self.session.post(base_url + "/u/dl2.pl", data=form_data, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        response.raise_for_status()
        html = await response.text()
        
        if "failed" in html:
            print(f"Captcha failed for {url}")
            return await self.get_download_info(url)
        
        with open("axfc_html.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        soup = BeautifulSoup(html, "html.parser")
        final_page = None
        for a in soup.find_all("a"):
            print(a.text)
            if "Download" in a.text:
                print("matched")
                download_url = a.get("href")
                final_page = download_url
                break
            
        # remove first . from final_page
        final_page = final_page[1:]
        print(f"base_url: {base_url}, final_page: {final_page}")
        response = await self.session.get(base_url +  "/u" + final_page,  headers={
            "Content-Type": "application/x-www-form-urlencoded"
        })
        response.raise_for_status()
        html = await response.text()
        soup = BeautifulSoup(html, "html.parser")
        download_url = None
        for a in soup.find_all("a"):
            if "download" in a.text:
                download_url = a.get("href")
                break
        
        if not download_url:
            raise ValueError("No download link found")
        
        response = await self.session.head(download_url)
        size = int(response.headers.get("Content-Length"))
        
        return DownloadInfo(
            filename=filename,
            size=size,
            download_url=download_url,
            headers={}
            )

if __name__ == "__main__":
    async def main():
        async with AxfcResolver() as resolver:
            download_info = await resolver.get_download_info("https://www.axfc.net/u/4085862")
        print(download_info)
    asyncio.run(main())