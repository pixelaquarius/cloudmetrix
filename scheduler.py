import time
import threading
import csv
import os
from datetime import datetime
import uploader

class AutoPostManager:
    def __init__(self, data_file):
        self.is_running = False
        self.interval = 5 * 60  # Polling cycle: 5 minutes
        self.data_file = data_file
        self.base_dir = os.path.dirname(os.path.abspath(data_file))

    def start_automation(self):
        if not self.is_running:
            self.is_running = True
            thread = threading.Thread(target=self._loop, daemon=True)
            thread.start()

    def _loop(self):
        print(f"[{datetime.now()}] AutoPostManager Thread started. Checking queue every 5 mins...")
        while self.is_running:
            try:
                self.check_and_post()
            except Exception as e:
                print(f"AutoPostManager Error: {e}")
            time.sleep(self.interval)

    def check_and_post(self):
        if not os.path.exists(self.data_file):
            return
            
        rows = []
        with open(self.data_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
            
        updated = False
        now = datetime.now()
        
        for row in rows:
            if row.get('status') == 'Scheduled' and row.get('scheduled_time'):
                try:
                    sched_time = datetime.fromisoformat(row['scheduled_time'].replace('Z', '+00:00'))
                    # Normalize both to naive (no timezone) for comparison
                    if sched_time.tzinfo is not None:
                        sched_time = sched_time.replace(tzinfo=None)
                        
                    # If time matches or has surpassed
                    if now >= sched_time:
                        print(f"[{datetime.now()}] >> FIRE: Executing scheduled job for {row.get('filename')}")
                        
                        # ==========================================================
                        # FACEBOOK FANPAGE UPLOADER
                        # ==========================================================
                        print(f"--> Booting Fanpage Uploader for {row.get('title')}...")
                        # JIT Download Check
                        video_path = os.path.join(self.base_dir, 'downloads', row['filename'])
                        source_url = row.get('source_url', '')
                        
                        if not os.path.exists(video_path) and source_url:
                            print(f"[AutoPost] Fetching JIT Video from {source_url}...")
                            import downloader
                            success_dl = downloader.download_video_jit(source_url, video_path)
                            if not success_dl:
                                print(f"[AutoPost] JIT Download failed, skipping post: {row['filename']}")
                                continue
                                
                        if not os.path.exists(video_path):
                            print(f"[AutoPost] Missing media file: {video_path}")
                            continue
                            
                        # Ghép Caption và Hashtags
                        caption_text = row.get('caption', row.get('title', ''))
                        hashtags = row.get('hashtags', '')
                        profile = row.get('profile')
                        if not profile or profile == 'Default':
                            # Dynamic fallback to first available account
                            accounts_file = os.path.join(self.base_dir, 'accounts.json')
                            if os.path.exists(accounts_file):
                                import json
                                try:
                                    with open(accounts_file, 'r', encoding='utf-8') as f:
                                        accs = json.load(f)
                                        if accs: profile = accs[0]['profile']
                                        else: profile = 'Automation_1'
                                except: profile = 'Automation_1'
                            else:
                                profile = 'Automation_1'

                        full_content = caption_text + "\n\n" + hashtags
                        
                        import uploader
                        success = uploader.upload_to_facebook_page(video_path, full_content, profile_name=profile)
                        
                        if success:
                            row['status'] = 'Done'
                            updated = True
                        else:
                            row['status'] = 'Failed'
                            updated = True
                        
                        # Chỉ xử lý 1 video trong mỗi vòng lặp 5 phút để tránh spam TikTok
                        break  
                except ValueError:
                    continue
                    
        # Nếu có cập nhật trạng thái (đã đăng xong) thì ghi đè lại file CSV
        if updated and headers:
            with open(self.data_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)