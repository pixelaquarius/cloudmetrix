import os
import csv
import json
from datetime import datetime
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
import uuid
import threading
import downloader
import scheduler
import playwright_uploader
import threading

app = Flask(__name__)

CSV_LOCK = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'content_map.csv')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {"fb_page_id": "", "fb_access_token": ""}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except:
            return {"fb_page_id": "", "fb_access_token": ""}

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def init_db():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    th_dir = os.path.join(DATA_DIR, 'thumbnails')
    if not os.path.exists(th_dir):
        os.makedirs(th_dir, exist_ok=True)
    
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # headers: id, filename, title, caption, hashtags, profile, status, downloaded_at, scheduled_time, thumbnail_path, source_url
            # headers: id, filename, title, caption, hashtags, profile, status, downloaded_at, scheduled_time, thumbnail_path, source_url, bypass_copyright
            writer.writerow(['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright'])
            # Create a clean mock entry
            writer.writerow(['m1', 'tiktok_trend_1.mp4', 'Wait for the end!', 'Wait for the end! #fyp #trending', '#fyp, #trending', 'Automation_1', 'Pending', datetime.now().isoformat(), '', '', '', '0'])

init_db()

@app.route('/')
def index():
    from flask import redirect
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    # Pass some dummy statistics for the dashboard
    import glob
    videos_count = len(glob.glob(os.path.join(DATA_DIR, 'downloads', '*.*')))
    
    csv_rows = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            csv_rows = list(csv.DictReader(f))
            
    posted = sum(1 for r in csv_rows if r.get('status') == 'Done')
    pending = sum(1 for r in csv_rows if r.get('status') == 'Pending')
    scheduled = sum(1 for r in csv_rows if r.get('status') == 'Scheduled')
    
    return render_template('dashboard.html', 
                           videos_count=videos_count, 
                           posted=posted, 
                           pending=pending, 
                           scheduled=scheduled,
                           total_queue=len(csv_rows))

@app.route('/data/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    return send_from_directory(os.path.join(DATA_DIR, 'thumbnails'), filename)

@app.route('/data/downloads/<path:filename>')
def serve_video(filename):
    return send_from_directory(os.path.join(DATA_DIR, 'downloads'), filename)

@app.route('/downloader')
def downloader_page():
    return render_template('downloader.html')

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/editor')
def editor():
    return render_template('editor.html')

@app.route('/publisher')
def publisher():
    return render_template('publisher.html')

@app.route('/accounts')
def accounts():
    return render_template('accounts.html')

@app.route('/calendar')
def calendar():
    return render_template('calendar.html')

@app.route('/api/load-csv', methods=['GET'])
def load_csv():
    rows = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Sanitize: remove None keys, convert None values to ''
                clean_row = {str(k): (v if v is not None else '') for k, v in row.items() if k is not None}
                rows.append(clean_row)
    return jsonify({"rows": rows})

@app.route('/api/save-csv', methods=['POST'])
def save_csv():
    data = request.json
    updated_rows = data['rows']
    
    if updated_rows is not None:
        headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
        with CSV_LOCK:
            with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for row in updated_rows:
                    safe_row = {h: row.get(h, '') for h in headers}
                    writer.writerow(safe_row)
                
    return jsonify({"success": True, "message": "Updated successfully"})

@app.route('/api/sync', methods=['POST'])
def api_sync():
    data = request.json
    url = data.get('url')
    limit = int(data.get('limit', 5))
    mode = data.get('mode', 'auto')
    
    if not url:
        return jsonify({"error": "URL required"}), 400
        
    def background_download():
        print(f"Background Sync Started for {url}")
        
        # Generator based incremental sync
        sync_generator = downloader.sync_tiktok(url, limit, DATA_DIR, os.path.join(DATA_DIR, 'thumbnails'))
        
        headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
        
        records_found = 0
        for rec in sync_generator:
            records_found += 1
            
            if mode == 'preview':
                # State is updated inside sync_tiktok for preview results
                continue

            # Incremental Save Mode
            with CSV_LOCK:
                if not os.path.exists(DATA_FILE):
                     with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
                         writer = csv.DictWriter(f, fieldnames=headers)
                         writer.writeheader()
                         
                with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=headers)
                    writer.writerow({
                        'id': str(uuid.uuid4())[:8],
                        'filename': rec['filename'],
                        'title': rec['title'],
                        'caption': rec['title'],
                        'hashtags': '',
                        'profile': 'Automation_1',
                        'status': 'Pending',
                        'downloaded_at': datetime.now().isoformat(),
                        'scheduled_time': '',
                        'thumbnail_path': rec['thumbnail_path'],
                        'source_url': rec['source_url']
                    })
            print(f"Incremental Sync: Added {rec['filename']}")
            
        if mode == 'preview':
            downloader.DOWNLOAD_STATE['status'] = 'preview_ready'
            print(f"Preview Ready! Waiting for user selection.")

        print(f"Background Sync Completed! Processed {records_found} videos.")
                
    threading.Thread(target=background_download, daemon=True).start()
    return jsonify({"success": True, "message": "Sync job dispatched. Awaiting process."})

@app.route('/api/smart-sync', methods=['POST'])
def api_smart_sync():
    data = request.json
    url = data.get('url')
    if not url: return jsonify({"error": "URL required"}), 400
    
    def background_smart_sync():
        import asyncio
        from interceptor_downloader import TikTokSmartDownloader
        import uploader
        
        uploader.POST_STATE['status'] = 'running'
        uploader.POST_STATE['logs'] = [f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ Smart Sync Interceptor: {url[:30]}..."]
        
        downloader_obj = TikTokSmartDownloader(headless=True)
        
        async def run_sync():
            v_url, meta = await downloader_obj.fetch_media_and_metadata(url)
            if v_url:
                timestamp = int(time.time())
                filename = f"smart_{timestamp}.mp4"
                save_path = os.path.join(DATA_DIR, 'downloads', filename)
                
                if downloader_obj.download_file(v_url, save_path):
                    # Add to CSV
                    headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
                    with CSV_LOCK:
                        with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
                            writer = csv.DictWriter(f, fieldnames=headers)
                            writer.writerow({
                                'id': str(uuid.uuid4())[:8],
                                'filename': filename,
                                'title': meta.get('title', 'Smart Asset'),
                                'caption': meta.get('description', ''),
                                'hashtags': '',
                                'profile': 'Automation_1',
                                'status': 'Pending',
                                'downloaded_at': datetime.now().isoformat(),
                                'scheduled_time': '',
                                'thumbnail_path': '',
                                'source_url': url,
                                'bypass_copyright': '0'
                            })
                    uploader.log_post("✅ Smart Sync complete! Asset added to queue.")
                else:
                    uploader.log_post("❌ Download failed in Smart Sync.")
            else:
                uploader.log_post("❌ Interceptor failed to catch stream.")
            
            uploader.POST_STATE['status'] = 'idle'

        # Run async in thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_sync())
        loop.close()

    threading.Thread(target=background_smart_sync, daemon=True).start()
    return jsonify({"success": True, "message": "Smart sync job dispatched."})

@app.route('/api/save-preview', methods=['POST'])
def api_save_preview():
    data = request.json
    selected_records = data.get('records', [])
    
    if not selected_records:
        return jsonify({"error": "No records provided"}), 400
        
    headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
    if not os.path.exists(DATA_FILE):
         with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
             writer = csv.DictWriter(f, fieldnames=headers)
             writer.writeheader()
             
    with open(DATA_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        for rec in selected_records:
            writer.writerow({
                'id': str(uuid.uuid4())[:8],
                'filename': rec['filename'],
                'title': rec['title'],
                'caption': rec['title'],
                'hashtags': '',
                'profile': 'Automation_1',
                'status': 'Pending',
                'downloaded_at': datetime.now().isoformat(),
                'scheduled_time': '',
                'thumbnail_path': rec['thumbnail_path'],
                'source_url': rec.get('source_url', '')
            })
            
    downloader.DOWNLOAD_STATE['status'] = 'idle'
    downloader.DOWNLOAD_STATE['results'] = []
    
    return jsonify({"success": True, "message": f"Saved {len(selected_records)} items to queue."})

@app.route('/api/download-progress')
def get_download_progress():
    state = downloader.DOWNLOAD_STATE.copy()
    # Sanitize results list - ensure all keys/values are strings
    clean_results = []
    for rec in state.get('results', []):
        if isinstance(rec, dict):
            clean_results.append({str(k): (str(v) if v is not None else '') for k, v in rec.items() if k is not None})
    state['results'] = clean_results
    state['logs'] = [str(l) for l in state.get('logs', [])]
    return jsonify(state)

@app.route('/api/post-progress')
def get_post_progress():
    # Import uploader at top level once or use a consistent reference
    import uploader
    state = uploader.POST_STATE.copy()
    # Ensure logs are serialized properly
    if 'logs' in state:
        state['logs'] = [str(l) for l in state['logs']]
    return jsonify(state)

@app.route('/api/post-now', methods=['POST'])
def api_post_now():
    data = request.json
    filename = data.get('filename')
    title = data.get('title')
    source_url = data.get('source_url', '')
    profile = data.get('profile')
    transform = data.get('transform', False) # New flag
    if not profile or profile == 'Automation_1':
        # Dynamic fallback to first available account
        if os.path.exists(ACCOUNTS_FILE):
             with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                 accs = json.load(f)
                 if accs: profile = accs[0]['profile']
                 else: profile = 'Automation_1'
        else:
            profile = 'Automation_1'
    
    if not filename:
        return jsonify({"error": "No filename provided"}), 400
        
    import uploader
    # Reset and set running status immediately for UI feedback
    uploader.POST_STATE['status'] = 'running'
    uploader.POST_STATE['logs'] = [f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Deployment sequence initiated..."]
    uploader.POST_STATE['progress'] = 5
    uploader.POST_STATE['filename'] = filename

    def manual_post():
        try:
            import uploader
            import downloader
            # INITIAL PATH SETUP
            working_filename = filename
            working_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', working_filename))
            
            # JUST-IN-TIME (JIT) DOWNLOAD & FORMAT CONVERSION
            is_legacy = any(working_filename.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.wav'])
            if is_legacy:
                # Force .mp4 extension for legacy/broken downloads
                working_filename = os.path.splitext(working_filename)[0] + ".mp4"
                working_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', working_filename))

            if (not os.path.exists(working_path) or is_legacy) and source_url:
                uploader.log_post(f"JIT Engine: Fetching target media (Format Fix) from {source_url}...")
                success = downloader.download_video_jit(source_url, working_path)
                if not success:
                    uploader.log_post("❌ JIT Media extraction failed!")
                    return
            
            if not os.path.exists(working_path):
                # Check for the file again without spaces or check directory
                uploader.log_post(f"❌ Media file not found at: {working_path}")
                # List files to help debug
                files_in_dir = os.listdir(os.path.join(DATA_DIR, 'downloads'))
                uploader.log_post(f"Debug: Files in downloads: {files_in_dir[:5]}... Total: {len(files_in_dir)}")
                return
                
            # COPYRIGHT BYPASS (TRANSFORMATION)
            if transform:
                from video_transformer import VideoTransformer
                uploader.log_post("🛡️ Copyright Bypass: Applying Video Filters (Flip, Crop, Speed)...", progress=30)
                transformed_filename = "bypass_" + working_filename
                transformed_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', transformed_filename))
                
                transformer = VideoTransformer()
                trans_success = transformer.apply_bypass_filters(working_path, transformed_path)
                if trans_success:
                    uploader.log_post("✅ Transformation complete! Using modified asset.", progress=60)
                    working_path = transformed_path
                    working_filename = transformed_filename
                else:
                    uploader.log_post("⚠️ Transformation failed. Proceeding with original asset.")

            success = uploader.upload_to_facebook_page(working_path, title, profile_name=profile)
            
            if success:
                # Update CSV status to Done and update filename if it changed
                if os.path.exists(DATA_FILE):
                    with CSV_LOCK:
                        with open(DATA_FILE, 'r', encoding='utf-8') as f:
                            rows = list(csv.DictReader(f))
                        for r in rows:
                            if r.get('filename') == filename: # Use original filename to find the row
                                r['status'] = 'Done'
                                r['filename'] = working_filename # Update to new .mp4 filename
                        headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
                        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
                            writer = csv.DictWriter(f, fieldnames=headers)
                            writer.writeheader()
                            writer.writerows(rows)
                uploader.log_post("🎉 MANUAL POST COMPLETED!")
            else:
                # Update CSV status to Failed
                if os.path.exists(DATA_FILE):
                    with CSV_LOCK:
                        with open(DATA_FILE, 'r', encoding='utf-8') as f:
                            rows = list(csv.DictReader(f))
                        for r in rows:
                            if r.get('filename') == filename:
                                r['status'] = 'Failed'
                        headers = ['id', 'filename', 'title', 'caption', 'hashtags', 'profile', 'status', 'downloaded_at', 'scheduled_time', 'thumbnail_path', 'source_url', 'bypass_copyright']
                        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
                            writer = csv.DictWriter(f, fieldnames=headers)
                            writer.writeheader()
                            writer.writerows(rows)
                uploader.log_post("❌ Upload failed. Please check the uploader logs.")
        except Exception as e:
            import uploader
            uploader.log_post(f"CRITICAL ENGINE ERROR: {e}")
            uploader.POST_STATE['status'] = 'idle'
                    
    threading.Thread(target=manual_post).start()
    return jsonify({"success": True, "message": "Triggered manual Selenium sequence."})

@app.route('/api/video/<filename>', methods=['DELETE'])
def delete_video(filename):
    if os.path.exists(DATA_FILE):
        rows = []
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)
            
        new_rows = [r for r in rows if r.get('filename') != filename]
        
        with open(DATA_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(new_rows)
            
    # Remove physical file
    import os
    video_path = os.path.join(DATA_DIR, 'downloads', filename)
    if os.path.exists(video_path):
        os.remove(video_path)
        
    return jsonify({"success": True})

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'GET':
        return jsonify(load_config())
    elif request.method == 'POST':
        data = request.json
        # Merge with existing
        cfg = load_config()
        cfg.update(data)
        save_config(cfg)
        return jsonify({"success": True, "message": "Settings saved"})

@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return jsonify({"accounts": []})
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
        return jsonify({"accounts": json.load(f)})

@app.route('/api/accounts', methods=['POST'])
def api_add_account():
    data = request.json
    name = data.get('name')
    if not name: return jsonify({"error": "Name required"}), 400
    
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
            
    new_acc = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "profile": "".join([c for c in name if c.isalnum() or c in ('_', '-')]).strip(),
        "status": "Ready"
    }
    accounts.append(new_acc)
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=4)
        
    return jsonify({"success": True, "account": new_acc})

@app.route('/api/accounts/<acc_id>', methods=['DELETE'])
def api_delete_account(acc_id):
    if not os.path.exists(ACCOUNTS_FILE): return jsonify({"error": "No accounts"}), 404
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    # Also clean up the profile directory if we want? Maybe too risky.
    new_accounts = [a for a in accounts if a['id'] != acc_id]
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(new_accounts, f, indent=4)
    return jsonify({"success": True})

@app.route('/api/accounts/setup/<acc_id>', methods=['POST'])
def api_setup_account(acc_id):
    if not os.path.exists(ACCOUNTS_FILE): return jsonify({"error": "No accounts"}), 404
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc: return jsonify({"error": "Account not found"}), 404
    
    def launch_setup():
        from playwright.sync_api import sync_playwright
        profile_path = playwright_uploader.get_user_data_dir(acc['profile'])
        with sync_playwright() as p:
            # Launch VISIBLE browser for user to login
            browser = p.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            page.goto("https://business.facebook.com/latest/composer")
            print(f"Setup session active for {acc['name']}. Waiting for browser to close...")
            # Browser stays open until user closes it
            while True:
                try: 
                    if not browser.is_connected() or len(browser.pages) == 0: break
                    time.sleep(1)
                except: break
            print(f"Setup session finished for {acc['name']}.")
            browser.close()

    threading.Thread(target=launch_setup, daemon=True).start()
    return jsonify({"success": True, "message": "Browser opened for setup. Please login manually."})

@app.route('/api/launch-login', methods=['POST'])
def api_launch_login_alias():
    # Frontend uses /api/launch-login, map it to the existing setup logic
    data = request.json
    profile = data.get('profile')
    if not os.path.exists(ACCOUNTS_FILE): return jsonify({"error": "No accounts"}), 404
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    acc = next((a for a in accounts if a['profile'] == profile), None)
    if not acc: return jsonify({"error": "Account not found"}), 404
    return api_setup_account(acc['id'])

@app.route('/api/accounts/verify-login', methods=['POST'])
def api_verify_account_login():
    data = request.json
    acc_id = data.get('id')
    if not os.path.exists(ACCOUNTS_FILE): return jsonify({"error": "No accounts"}), 404
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
        accounts = json.load(f)
    
    acc = next((a for a in accounts if a['id'] == acc_id), None)
    if not acc: return jsonify({"error": "Account not found"}), 404

    def do_verify():
        # Update status to checking
        acc['status'] = "Checking..."
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(accounts, f, indent=4)
            
        # Re-load to get latest state in thread
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            thread_accounts = json.load(f)
        thread_acc = next((a for a in thread_accounts if a['id'] == acc_id), None)
        
        status = playwright_uploader.verify_facebook_login(acc['profile'])
        thread_acc['status'] = status
        thread_acc['last_verified'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(thread_accounts, f, indent=4)

    threading.Thread(target=do_verify, daemon=True).start()
    return jsonify({"success": True, "message": "Verification started in background."})


@app.route('/api/download_jit_preview', methods=['POST'])
def download_jit_preview():
    data = request.json
    source_url = data.get('source_url')
    filename = data.get('filename')
    
    if not filename:
        return jsonify({"error": "Missing filename"}), 400
        
    filepath = os.path.join(DATA_DIR, 'downloads', filename)
    if os.path.exists(filepath):
        return jsonify({"success": True, "status": "exists", "url": f"/data/downloads/{filename}"})
        
    if not source_url:
        return jsonify({"error": "Missing source URL for JIT download"}), 400
        
    try:
        success = downloader.download_video_jit(source_url, filepath)
        if success:
            return jsonify({"success": True, "status": "downloaded", "url": f"/data/downloads/{filename}"})
        else:
            return jsonify({"error": "Failed to extract media from source."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    post_manager = scheduler.AutoPostManager(DATA_FILE)
    post_manager.start_automation()
    app.run(host='0.0.0.0', debug=True, port=5001)
