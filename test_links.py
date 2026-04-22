import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://www.tiktok.com/@reviewcamoi', wait_until='networkidle')
        links = await page.evaluate("Array.from(document.querySelectorAll('a')).map(a => a.href)")
        print([l for l in links if 'tiktok.com' in l])
        await browser.close()

asyncio.run(test())
