import os
import time
import requests
try:
    import cv2
except ImportError:
    cv2 = None
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
import asyncio
from tiktok_extractor import TikTokSmartExtractor

# Global State for Live Progress Tracking
DOWNLOAD_STATE = {
    "status": "idle",
    "logs": [],
    "progress_percent": 0,
    "total": 0,
    "current": 0,
    "results": []
}

def log_state(msg):
    DOWNLOAD_STATE["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    if len(DOWNLOAD_STATE["logs"]) > 20:
        DOWNLOAD_STATE["logs"].pop(0)
    print(msg)

def extract_thumbnail(video_path, thumbnail_dir):
    # Dùng cho phương pháp cũ (back-up). Khi dùng yt-dlp, ta sẽ fetch trực tiếp thumbnail từ URL
    try:
        if not os.path.exists(thumbnail_dir):
            os.makedirs(thumbnail_dir, exist_ok=True)
            
        base_name = os.path.basename(video_path).rsplit('.', 1)[0]
        thumb_path = os.path.join(thumbnail_dir, f"{base_name}.jpg")
        
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        if ret:
            height, width = frame.shape[:2]
            scale = 320 / float(width)
            dim = (320, int(height * scale))
            resized = cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)
            cv2.imwrite(thumb_path, resized)
        cap.release()
        return f"{base_name}.jpg"
    except Exception as e:
        log_state(f"Thumbnail error: {e}")
        return ""

def download_thumbnail_from_url(url, thumb_path):
    try:
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status()
        with open(thumb_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        log_state(f"Failed to fetch remote thumbnail: {e}")
        return False

def format_url(data):
    data = data.strip()
    if data.startswith("http"): return data
    uid = data if data.startswith("@") else f"@{data}"
    return f"https://www.tiktok.com/{uid}"

def sync_tiktok(target_url, max_videos=5, base_dir="data", thumbnail_dir="data/thumbnails"):
    DOWNLOAD_STATE["status"] = "running"
    DOWNLOAD_STATE["logs"] = []
    DOWNLOAD_STATE["progress_percent"] = 0
    DOWNLOAD_STATE["total"] = 0
    DOWNLOAD_STATE["current"] = 0
    
    url = format_url(target_url)
    extractor = TikTokSmartExtractor(download_dir=os.path.join(base_dir, "downloads"))
    
    log_state(f"🚀 Using TikTokSmartExtractor (Playwright + TikWM) for {url}")
    
    # 1. Scrape links using Playwright (running async in a sync context)
    try:
        video_links = asyncio.run(extractor.get_video_links(url, max_scroll_times=3))
    except Exception as e:
        log_state(f"❌ Scrape error: {e}")
        DOWNLOAD_STATE["status"] = "idle"
        return []

    if max_videos > 0 and len(video_links) > max_videos:
        video_links = video_links[:max_videos]

    total_videos = len(video_links)
    DOWNLOAD_STATE["total"] = total_videos
    
    if total_videos == 0:
        log_state("❌ No videos found. Module halted.")
        DOWNLOAD_STATE["status"] = "idle"
        return []

    log_state(f"Found {total_videos} videos. Processing through TikWM API...")
    
    folder_path = os.path.join(base_dir, "downloads")
    os.makedirs(folder_path, exist_ok=True)
    os.makedirs(thumbnail_dir, exist_ok=True)

    # 2. Process each video
    # Since we need to yield incrementally for the UI, we'll use a simplified version of fetch_cdn_and_download logic here
    import aiohttp
    
    async def process_batch():
        results = []
        async with aiohttp.ClientSession() as session:
            for i, v_link in enumerate(video_links):
                DOWNLOAD_STATE["current"] = i + 1
                DOWNLOAD_STATE["progress_percent"] = int(((i) / total_videos) * 100)
                
                video_id = v_link.rstrip('/').split('/')[-1]
                log_state(f"Processing [{i+1}/{total_videos}]: ID {video_id}")
                
                # Call TikWM API
                try:
                    async with session.get("https://www.tikwm.com/api/", params={"url": v_link}) as resp:
                        data = await resp.json()
                        if data.get("code") == 0:
                            item = data.get("data", {})
                            title = item.get("title", f"Video {video_id}")
                            thumb_url = item.get("cover")
                            
                            if thumb_url:
                                thumb_path = thumb_url # Save CDN URL directly
                            else:
                                thumb_path = ""
                            
                            record = {
                                "source_url": v_link,
                                "filename": f"{video_id}.mp4",
                                "title": title,
                                "thumbnail_path": thumb_path
                            }
                            
                            if "results" not in DOWNLOAD_STATE: DOWNLOAD_STATE["results"] = []
                            DOWNLOAD_STATE["results"].append(record)
                            results.append(record)
                        else:
                            log_state(f"⚠️ API Error for {video_id}: {data.get('msg')}")
                except Exception as e:
                    log_state(f"⚠️ Network error for {video_id}: {e}")
                
                # Human-like jitter
                await asyncio.sleep(random.uniform(1.0, 2.0))
        return results

    # Run the batch processing
    records = asyncio.run(process_batch())
    
    for rec in records:
        yield rec
                
    DOWNLOAD_STATE["progress_percent"] = 100
    DOWNLOAD_STATE["status"] = "idle"
    log_state(f"✅ Metadata sync for {total_videos} items complete.")

def download_video_jit(source_url, output_path):
    """
    Just-in-time download triggering right before automated posting using TikWM API.
    """
    try:
        import requests
        import random
        # Optional delay to be safe
        time.sleep(random.uniform(1, 2))
        
        api_url = f"https://www.tikwm.com/api/?url={source_url}"
        resp = requests.get(api_url).json()
        
        if resp.get("code") == 0:
            cdn_url = resp.get("data", {}).get("play")
            if cdn_url:
                v_resp = requests.get(cdn_url, stream=True)
                if v_resp.status_code == 200:
                    with open(output_path, 'wb') as f:
                        for chunk in v_resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
        return False
    except Exception as e:
        print(f"JIT Download Failed via TikWM: {e}")
        return False
