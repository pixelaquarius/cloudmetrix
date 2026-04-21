import os
import asyncio
import random
import time
import json
import aiohttp
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from datetime import datetime

# --- CONFIGURATION ---
DOWNLOAD_DIR = "downloads"
TIKWM_API_URL = "https://www.tikwm.com/api/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

class TikTokSmartExtractor:
    def __init__(self, download_dir=DOWNLOAD_DIR):
        self.download_dir = download_dir
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
            print(f"[*] Created directory: {self.download_dir}")

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def get_video_links(self, channel_url, max_scroll_times=3, max_videos=10):
        """
        Sử dụng Playwright để cuộn trang và trích xuất link video thô.
        """
        self.log(f"🚀 Bắt đầu quét kênh: {channel_url}")
        video_urls = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            try:
                self.log(f"Navigating to {channel_url}...")
                await page.goto(channel_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(5) # Solid initial wait
                
                # Wait for the post grid to be available
                for grid_sel in ["div[data-e2e='user-post-item-list']", "div.eip9vu0", "div.css-1698e6e"]:
                    try:
                        await page.wait_for_selector(grid_sel, timeout=15000)
                        self.log(f"✅ Grid detected via: {grid_sel}")
                        break
                    except: continue

                # Vòng lặp cuộn trang
                for i in range(max_scroll_times):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(3) 
                    self.log(f"   - Lần cuộn {i+1}/{max_scroll_times}")
                
                # Final link collection via evaluation
                await page.screenshot(path="scratch/tiktok_grid_debug.png", full_page=True)
                video_urls_list = await page.evaluate("""
                    () => {
                        const links = Array.from(document.querySelectorAll('a'));
                        return links
                            .filter(a => a.href.includes('/video/'))
                            .map(a => a.href.split('?')[0]);
                    }
                """)
                
                for url in video_urls_list:
                    video_urls.add(url)

                self.log(f"✅ Tìm thấy {len(video_urls)} link video duy nhất.")
                
            finally:
                await browser.close()
        
        return list(video_urls)[:max_videos]

    async def fetch_cdn_and_download(self, session, video_url):
        """
        Gọi API TikWM để giải mã và tải video không logo.
        """
        video_id = video_url.rstrip('/').split('/')[-1]
        save_path = os.path.join(self.download_dir, f"{video_id}.mp4")

        if os.path.exists(save_path):
            self.log(f"⏩ Đã tồn tại: {video_id}.mp4. Bỏ qua.")
            return

        try:
            # 1. Gọi API TikWM
            api_params = {"url": video_url}
            async with session.get(TIKWM_API_URL, params=api_params) as response:
                if response.status != 200:
                    self.log(f"⚠️ TikWM API lỗi HTTP {response.status} cho ID {video_id}")
                    return

                data = await response.json()
                if data.get("code") != 0:
                    self.log(f"⚠️ TikWM báo lỗi (Code {data.get('code')}): {data.get('msg')}")
                    return

                cdn_url = data.get("data", {}).get("play")
                if not cdn_url:
                    self.log(f"⚠️ Không tìm thấy link CDN cho ID {video_id}")
                    return

            # 2. Tải video
            self.log(f"📥 Đang tải: {video_id}.mp4 ...")
            async with session.get(cdn_url) as video_resp:
                if video_resp.status == 200:
                    with open(save_path, "wb") as f:
                        while True:
                            chunk = await video_resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                    self.log(f"✨ Thành công: {video_id}.mp4")
                else:
                    self.log(f"⚠️ Lỗi tải file CDN: HTTP {video_resp.status}")

        except Exception as e:
            self.log(f"❌ Lỗi xử lý video {video_id}: {e}")

    async def run(self, channel_url, max_scroll_times=3):
        # Bước 1: Cào link
        video_links = await self.get_video_links(channel_url, max_scroll_times)
        
        if not video_links:
            self.log("ℹ️ Không tìm thấy video nào để tải.")
            return

        # Bước 2 & 3: Giải mã & Tải về
        self.log(f"🛠 Bắt đầu xử lý {len(video_links)} video...")
        async with aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}) as session:
            for i, link in enumerate(video_links):
                # Thử-sai từng video để không làm dừng chương trình
                await self.fetch_cdn_and_download(session, link)
                
                # Human-like delay
                if i < len(video_links) - 1:
                    delay = random.uniform(1.5, 3.5)
                    self.log(f"😴 Nghỉ {delay:.1f}s để tránh bị chặn...")
                    await asyncio.sleep(delay)

        self.log("🏁 Hoàn tất toàn bộ công việc!")

async def main(channel_url, max_scroll_times=3):
    extractor = TikTokSmartExtractor()
    await extractor.run(channel_url, max_scroll_times)

if __name__ == "__main__":
    import sys
    # Cho phép truyền URL qua tham số dòng lệnh hoặc dùng mặc định
    target_channel = sys.argv[1] if len(sys.argv) > 1 else "https://www.tiktok.com/@jelly.here10"
    scroll_count = int(sys.argv[2]) if len(sys.argv) > 3 else 3
    
    asyncio.run(main(target_channel, scroll_count))
