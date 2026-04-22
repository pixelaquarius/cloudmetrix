import os
import json
import uuid
from datetime import datetime
import time
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from sqlalchemy import select, delete

# Import Database Models
from database.models import sync_session, VideoAsset, AssetStatus, init_db

# Import Workers
from workers.tasks import manual_post_task, background_smart_sync_task
from workers.huey_app import huey

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cloudmetrix_secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')

# Initialize DB on startup
import asyncio
def setup_db():
    asyncio.run(init_db())
setup_db()

@app.route('/')
def index():
    from flask import redirect
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    import glob
    videos_count = len(glob.glob(os.path.join(DATA_DIR, 'downloads', '*.*')))
    
    with sync_session() as session:
        result = session.execute(select(VideoAsset.status))
        rows = result.scalars().all()
        
    posted = sum(1 for r in rows if r in (AssetStatus.DONE, AssetStatus.PUBLISHED, AssetStatus.SEEDED))
    pending = sum(1 for r in rows if r == AssetStatus.PENDING)
    scheduled = sum(1 for r in rows if r == AssetStatus.SCHEDULED)
    
    return render_template('dashboard.html', 
                           videos_count=videos_count, 
                           posted=posted, 
                           pending=pending, 
                           scheduled=scheduled,
                           total_queue=len(rows))

@app.route('/data/<path:subpath>/<path:filename>')
def serve_data(subpath, filename):
    return send_from_directory(os.path.join(DATA_DIR, subpath), filename)

@app.route('/downloader')
def downloader_page(): return render_template('downloader.html')

@app.route('/settings')
def settings_page(): return render_template('settings.html')

@app.route('/editor')
def editor(): return render_template('editor.html')

@app.route('/publisher')
def publisher(): return render_template('publisher.html')

@app.route('/accounts')
def accounts(): return render_template('accounts.html')

@app.route('/calendar')
def calendar(): return render_template('calendar.html')

@app.route('/api/load-csv', methods=['GET'])
def load_assets():
    """ Now using Sync Database Query instead of CSV """
    with sync_session() as session:
        result = session.execute(select(VideoAsset))
        assets = result.scalars().all()
        rows = [
            {
                "id": a.id, "filename": a.filename, "title": a.title,
                "caption": a.caption, "hashtags": a.hashtags, "profile": a.profile,
                "status": a.status.value if a.status else "Pending",
                "downloaded_at": a.downloaded_at.isoformat() if a.downloaded_at else "",
                "scheduled_time": a.scheduled_time.isoformat() if a.scheduled_time else "",
                "thumbnail_path": a.thumbnail_path, "source_url": a.source_url,
                "bypass_copyright": a.bypass_copyright, "affiliate_link": a.affiliate_link,
                "ab_test_group": a.ab_test_group
            } for a in assets
        ]
    return jsonify({"rows": rows})

@app.route('/api/save-csv', methods=['POST'])
def save_assets():
    data = request.json
    updated_rows = data.get('rows', [])
    
    with sync_session() as session:
        for row in updated_rows:
            result = session.execute(select(VideoAsset).where(VideoAsset.id == row['id']))
            asset = result.scalar_one_or_none()
            if asset:
                asset.title = row.get('title', asset.title)
                asset.caption = row.get('caption', asset.caption)
                asset.hashtags = row.get('hashtags', asset.hashtags)
                asset.profile = row.get('profile', asset.profile)
                try:
                    asset.status = AssetStatus(row.get('status', 'Pending'))
                except: pass
                asset.bypass_copyright = row.get('bypass_copyright', asset.bypass_copyright)
                asset.affiliate_link = row.get('affiliate_link', asset.affiliate_link)
        session.commit()

    return jsonify({"success": True, "message": "Updated successfully"})

@app.route('/api/smart-sync', methods=['POST'])
def api_smart_sync():
    url = request.json.get('url')
    if not url: return jsonify({"error": "URL required"}), 400
    background_smart_sync_task(url)
    return jsonify({"success": True, "message": "Smart sync job dispatched to Huey."})

# --- PHASE 1: Downloader Routes ---
@app.route('/api/sync', methods=['POST'])
def api_sync():
    """ Trigger discovery stage only. """
    url = request.json.get('url')
    if not url: return jsonify({"error": "URL required"}), 400
    background_smart_sync_task(url)
    return jsonify({"success": True, "message": "Discovery job dispatched to Huey."})

@app.route('/api/download-progress', methods=['GET'])
def api_download_progress():
    """ Return discovery progress to UI """
    # Placeholder for Phase 5 progress tracking
    return jsonify({"status": "idle", "progress": 0, "logs": []})

@app.route('/api/post-now', methods=['POST'])
def api_post_now():
    data = request.json
    filename = data.get('filename')
    title = data.get('title')
    source_url = data.get('source_url', '')
    profile = data.get('profile', 'Automation_1')
    transform = data.get('transform', False)
    affiliate_link = data.get('affiliate_link', '')
    
    if not filename: return jsonify({"error": "No filename provided"}), 400
    
    socketio.emit('post_update', {"status": "running", "filename": filename, "logs": ["🚀 Deployment sequence initiated..."], "progress": 5})

    # Dispatch to Huey
    manual_post_task(filename, title, source_url, profile, transform, affiliate_link)
    
    return jsonify({"success": True, "message": "Triggered manual Selenium sequence via Huey."})

@app.route('/api/video/<filename>', methods=['DELETE'])
def delete_video(filename):
    with sync_session() as session:
        session.execute(delete(VideoAsset).where(VideoAsset.filename == filename))
        session.commit()
    
    video_path = os.path.join(DATA_DIR, 'downloads', filename)
    if os.path.exists(video_path): os.remove(video_path)
    return jsonify({"success": True})

@app.route('/api/internal/emit', methods=['POST'])
def internal_emit():
    """ Internal endpoint for Huey workers to trigger UI updates without File Locking """
    data = request.json
    socketio.emit('post_update', data)
    return jsonify({"success": True})

@socketio.on('connect')
def test_connect():
    emit('my response', {'data': 'Connected to WebSockets for live logs'})

# --- Account Routes ---
@app.route('/api/accounts', methods=['GET'])
def api_get_accounts():
    if not os.path.exists(ACCOUNTS_FILE): return jsonify({"accounts": []})
    with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f: return jsonify({"accounts": json.load(f)})

@app.route('/api/accounts', methods=['POST'])
def api_add_account():
    name = request.json.get('name')
    if not name: return jsonify({"error": "Name required"}), 400
    accounts = []
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f: accounts = json.load(f)
    new_acc = {
        "id": str(uuid.uuid4())[:8], "name": name,
        "profile": "".join([c for c in name if c.isalnum() or c in ('_', '-')]).strip(),
        "status": "Ready"
    }
    accounts.append(new_acc)
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f: json.dump(accounts, f, indent=4)
    return jsonify({"success": True, "account": new_acc})

# --- PHASE 1: Add Account Launch Route ---
@app.route('/api/launch-login', methods=['POST'])
def api_launch_login():
    data = request.json
    profile = data.get('profile')
    if not profile: return jsonify({"error": "Profile name required"}), 400
    
    import subprocess
    # Launch a simple headless=False playwright to scan QR code
    script_content = f"""
from playwright.sync_api import sync_playwright
import time
import os

profile_dir = os.path.abspath(os.path.join('data', 'browser_profiles', '{profile}'))
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
        channel="chrome"
    )
    page = browser.pages[0]
    page.goto('https://www.facebook.com/')
    print("Please login. The window will close in 3 minutes.")
    time.sleep(180)
    browser.close()
"""
    tmp_script = os.path.join(DATA_DIR, f"login_{profile}.py")
    with open(tmp_script, 'w', encoding='utf-8') as f:
        f.write(script_content)
        
    # Launch detached subprocess
    subprocess.Popen(['python', tmp_script], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
    
    return jsonify({"success": True, "message": f"Login window launched for profile {profile}"})

@app.route('/api/accounts/verify-login', methods=['POST'])
def api_verify_login():
    data = request.json
    profile = data.get('profile')
    if not profile: return jsonify({"error": "Profile name required"}), 400
    
    # Check if cookies exist for this profile
    user_data_dir = os.path.join(DATA_DIR, "browser_profiles", profile)
    status = "Verified" if os.path.exists(user_data_dir) else "Pending Login"
    
    return jsonify({"success": True, "status": status})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', debug=True, port=5001, allow_unsafe_werkzeug=True)
