import os
import time
import csv
import uuid
import sys
from dotenv import load_dotenv
import downloader
from video_transformer import VideoTransformer
from reels_uploader import FacebookReelsUploader

# Load environment
load_dotenv()
class ReupEngine:
    def __init__(self, profile=None):
        self.transformer = VideoTransformer(ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"))
        self.profile = profile or os.getenv("FB_PROFILE", "Automation_1")

    def cleanup_downloads(self):
        """Removes all files in the downloads directory."""
        import shutil
        folder = 'data/downloads'
        print(f"🧹 Cleaning up {folder}...")
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
        
    def process_single_link(self, tiktok_url, affiliate_link=None, asset_id=None):
        """
        Full Lifecycle: Download -> Transform -> Upload
        """
        print(f"\n--- [ENGINE] PROCESSING: {tiktok_url} ---")
        
        # 1. ROBUST EXTRACTION (TikWM API via downloader module)
        print(f"[Engine] Extracting metadata from {tiktok_url}...")
        try:
            # We use a simple requests call for single-link metadata in this sync context
            import requests
            api_url = f"https://www.tikwm.com/api/?url={tiktok_url}"
            resp = requests.get(api_url, timeout=15).json()
            
            if resp.get("code") == 0:
                data = resp.get("data", {})
                meta = {
                    "description": data.get("title", "Reup Content"),
                    "shop_link": None # TikWM API can sometimes provide this, but for now we default to None
                }
                print(f"✅ Metadata captured: {meta['description'][:50]}...")
            else:
                print(f"⚠️ API Warning: {resp.get('msg')}. Proceeding with default metadata.")
                meta = {"description": "Reup Content", "shop_link": None}
        except Exception as e:
            print(f"⚠️ Metadata extraction warning: {e}. Using defaults.")
            meta = {"description": "Reup Content", "shop_link": None}
            
        timestamp = int(time.time())
        raw_path = f"data/downloads/raw_{timestamp}.mp4"
        clean_path = f"data/downloads/clean_{timestamp}.mp4"
        
        if not downloader.download_video_jit(tiktok_url, raw_path):
            print("❌ STAGE 1 FAILED: Download error.")
            return False

        # 2. TRANSFORM (FFmpeg Bypass)
        if not self.transformer.apply_bypass_filters(raw_path, clean_path):
            print("❌ STAGE 2 FAILED: Transformation error.")
            return False

        # 3. UPLOAD (Reels Uploader)
        uploader = FacebookReelsUploader(profile_name=self.profile)
        
        # Retry loop for upload
        for attempt in range(3):
            print(f"🚀 Upload attempt {attempt + 1} for {tiktok_url}...")
            result = uploader.upload_reel(
                video_path=clean_path, 
                caption=meta.get("description", "Reup Content"), 
                affiliate_link=affiliate_link or meta.get("shop_link"),
                asset_id=asset_id
            )
            
            if result is True:
                # 4. VERIFICATION FEED CHECK
                print("⏳ Upload confirmed by Meta. Waiting 15s for feed publication...")
                time.sleep(15) # Give FB processing time before first check
                
                verified = False
                for v_attempt in range(3):
                    if uploader.verify_publication(meta.get("description", ""), asset_id=asset_id):
                        verified = True
                        break
                    print(f"⚠️ Verification pending (Attempt {v_attempt+1}/3). Retrying in 15s...")
                    time.sleep(15)
                
                if verified:
                    print(f"✅ [ENGINE] SUCCESS: {tiktok_url} is verified live!")
                    self._update_csv(tiktok_url, clean_path, meta.get("description", ""), "Done")
                else:
                    # If it uploaded but didn't verify, we shouldn't re-upload to avoid duplicates.
                    print(f"⚠️ [ENGINE] Post uploaded but not yet visible on feed. It may be under review.")
                    self._update_csv(tiktok_url, clean_path, meta.get("description", ""), "Pending Verification")
                    
                return True
                
            elif result == "SESSION_EXPIRED":
                self._update_csv(tiktok_url, clean_path, meta.get("description", ""), "Login Required")
                return "SESSION_EXPIRED"
            else:
                print(f"❌ [ENGINE] Upload failed on attempt {attempt + 1}. Retrying...")
                time.sleep(5)
                
        self._update_csv(tiktok_url, clean_path, meta.get("description", ""), "Failed")
        return False

    def _extract_video_id(self, url):
        import re
        match = re.search(r'/video/(\d+)', url)
        return match.group(1) if match else url

    def _get_uploaded_urls(self):
        data_file = "data/content_map.csv"
        video_ids = set()
        if not os.path.exists(data_file): return video_ids
        import csv
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('status') == 'Done' and row.get('source_url'):
                        vid_id = self._extract_video_id(row.get('source_url'))
                        video_ids.add(vid_id)
        except: pass
        return video_ids

    def _update_csv(self, url, filename, title, status):
        data_file = "data/content_map.csv"
        if not os.path.exists(data_file): return
        
        vid_id = self._extract_video_id(url)
        
        rows = []
        headers = []
        import csv
        with open(data_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
            
        found = False
        for row in rows:
            if self._extract_video_id(row.get('source_url', '')) == vid_id:
                row['status'] = status
                row['filename'] = os.path.basename(filename)
                found = True
                break
        
        if not found:
            # Add new record if not exists
            new_row = {h: '' for h in headers}
            new_row.update({
                'id': vid_id, # Track by true Video ID
                'filename': os.path.basename(filename),
                'title': title,
                'caption': title,
                'profile': self.profile,
                'status': status,
                'downloaded_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'source_url': url
            })
            rows.append(new_row)
            
        with open(data_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def batch_process_channel(self, tiktok_url, asset_id=None, count=10):
        """
        Scrapes a channel and processes N latest videos.
        """
        import asyncio
        from downloader import TikTokSmartExtractor
        
        print(f"📺 Batch processing channel: {tiktok_url} (Target: {count} videos)")
        self.cleanup_downloads()
        
        extractor = TikTokSmartExtractor()
        # Grab up to 50 links to ensure we have enough padding after filtering duplicates
        all_links = asyncio.run(extractor.get_video_links(tiktok_url, max_videos=50))
        
        uploaded_video_ids = self._get_uploaded_urls()
        
        links = []
        for url in all_links:
            vid = self._extract_video_id(url)
            if vid not in uploaded_video_ids:
                links.append(url)
                
        if len(links) > count:
            links = links[:count]

        
        print(f"🔗 Found {len(links)} links. Starting sequential processing...")
        
        results = {"success": 0, "failed": 0}
        for link in links:
            if self.process_single_link(link, asset_id=asset_id):
                results["success"] += 1
            else:
                results["failed"] += 1
        
        print(f"\n✨ Batch complete: {results['success']} Succeeded, {results['failed']} Failed.")
        return results

# Main Execution Entry
if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else None
    profile = sys.argv[2] if len(sys.argv) > 2 else None
    asset_id = sys.argv[3] if len(sys.argv) > 3 else None
    mode = sys.argv[4] if len(sys.argv) > 4 else "single"
    count = int(sys.argv[5]) if len(sys.argv) > 5 else 10
    
    if not url:
        print("Usage: python3 reup_engine.py <tiktok_url> [profile] [asset_id] [mode: single|batch] [count]")
    else:
        engine = ReupEngine(profile=profile)
        if mode == "batch":
            engine.batch_process_channel(url, asset_id=asset_id, count=count)
        else:
            engine.process_single_link(url, asset_id=asset_id)
