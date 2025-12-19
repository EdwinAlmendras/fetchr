from fetchr.config import DEBRID_GATEWAY
import aiohttp
import logging
logger = logging.getLogger(__name__)

async def get_direct_link(url: str):
    endpoint = f"{DEBRID_GATEWAY}/resolve/?url={url}"
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint) as response:
            response.raise_for_status()
            data = await response.json()
            reolved_url = data.get("url")
            if reolved_url:
                logger.debug(f"Download url... {reolved_url}")
                return reolved_url
            else:
                logger.error(f"Somethings wrong, {data.get('message')}")
                raise Exception(f"Somethings wrong, {data.get('message')}")