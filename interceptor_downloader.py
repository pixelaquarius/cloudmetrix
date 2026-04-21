import asyncio
import os
import re
import requests
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from datetime import datetime

class TikTokSmartDownloader:
    def __init__(self, headless=False):
        self.headless = headless
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"

    async def fetch_media_and_metadata(self, url):
        """
        Navigates to the TikTok URL and intercepts the network to find the direct MP4 URL.
        Also extracts metadata (caption, hashtags, shop link).
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            # Use a mobile-like context if needed, but Desktop is usually enough for interception
            context = await browser.new_context(user_agent=self.user_agent)
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            found_video_url = None
            metadata = {
                "title": "",
                "description": "",
                "hashtags": [],
                "shop_link": None
            }

            # --- Network Interruption Logic ---
            async def handle_response(response):
                nonlocal found_video_url
                if found_video_url: return
                
                url = response.url
                headers = response.headers
                content_type = headers.get("content-type", "")
                content_length = int(headers.get("content-length", 0))
                
                # Logic: Video type AND large body OR known TikTok media domain
                is_video = "video" in content_type
                is_large = content_length > 500000 # > 500KB
                
                if (is_video and is_large) or (re.search(r'/(video|v\d+)/', url) and is_large):
                    found_video_url = url
                    print(f"[Interceptor] ✅ Caught valid media stream ({content_length/1024/1024:.2f} MB): {url[:60]}...")

            page.on("response", handle_response)

            try:
                print(f"[Engine] Navigating to {url}...")
                # Use 'load' + manual wait to be more resilient
                await page.goto(url, wait_until="load", timeout=60000)
                
                # Simulate interaction to trigger video load
                await page.mouse.wheel(0, 500)
                await asyncio.sleep(2)
                
                # --- Metadata Extraction ---
                # Caption & Hashtag Extraction
                # TikTok uses data-e2e for reliable selectors
                caption_el = await page.wait_for_selector('[data-e2e="browse-video-desc"]', timeout=30000) or \
                             await page.wait_for_selector('//h1[contains(@class, "VideoCaption")]', timeout=5000)
                
                if caption_el:
                    metadata["description"] = await caption_el.inner_text()
                    metadata["hashtags"] = re.findall(r'#\w+', metadata["description"])
                
                # User/Title extraction
                title_el = await page.query_selector('[data-e2e="browse-user-title"]')
                if title_el:
                    metadata["title"] = await title_el.inner_text()
                
                # Shop Link Extraction (Product Card)
                shop_el = await page.query_selector('[data-e2e="product-card"]') or \
                          await page.query_selector('//a[contains(@href, "/product/")]')
                if shop_el:
                    metadata["shop_link"] = await shop_el.get_attribute("href")

                # Wait a bit more if video URL wasn't caught immediately
                if not found_video_url:
                    await asyncio.sleep(5)

            except Exception as e:
                print(f"❌ Navigation/Extraction error: {e}")
            finally:
                await browser.close()

            return found_video_url, metadata

    def download_file(self, video_url, output_path):
        """
        Downloads a video file from a direct URL using requests.
        """
        headers = {
            "User-Agent": self.user_agent,
            "Referer": "https://www.tiktok.com/"
        }
        try:
            print(f"[Downloader] Streaming from {video_url[:40]}...")
            with requests.get(video_url, headers=headers, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            print(f"✅ Saved to: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

# Quick Test logic
if __name__ == "__main__":
    test_url = "https://www.tiktok.com/@jelly.here10/video/7617154288313306388"
    out = "scratch/test_interception.mp4"
    downloader = TikTokSmartDownloader(headless=True)
    
    async def run_test():
        v_url, meta = await downloader.fetch_media_and_metadata(test_url)
        if v_url:
            print(f"Found Metadata: {meta}")
            downloader.download_file(v_url, out)
        else:
            print("Failed to catch video URL.")

    asyncio.run(run_test())
