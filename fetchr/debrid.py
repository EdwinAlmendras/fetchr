from fetchr.config import REALDEBRID_BEARER_TOKEN


async def get_direct_link(link: str):
    import aiohttp
    url = "https://app.real-debrid.com/rest/1.0/unrestrict/link"
    headers = {
        "Authorization": f"Bearer {REALDEBRID_BEARER_TOKEN}",
        "Accept": "*/*",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "link": link,
        "password": ""
    }
    
    session = aiohttp.ClientSession()
    resp = await session.post(url, headers=headers, data=data, timeout=15)
    resp.raise_for_status()
    response = await resp.json()
    await session.close()
    return response["download"]
