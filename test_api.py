import asyncio
from playwright.async_api import async_playwright
import json

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.tikwm.com/api/user/posts?unique_id=reviewcamoi&count=10')
        content = await page.evaluate("document.body.innerText")
        print(content[:500])
        await browser.close()

asyncio.run(test())
