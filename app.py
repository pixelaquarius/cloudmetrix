import os
import json
import uuid
from datetime import datetime
import time
import asyncio
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename

# Import Database Models
from database.models import get_session, VideoAsset, AssetStatus, engine, async_session, init_db

# Import Workers
from workers.tasks import manual_post_task, background_smart_sync_task
from workers.huey_app import huey

import downloader
import playwright_uploader

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cloudmetrix_secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_FILE = os.path.join(DATA_DIR, 'config.json')
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
STATE_FILE = os.path.join(DATA_DIR, 'post_state.json')

# Initialize Async DB on startup
def setup_db():
    asyncio.run(init_db())
setup_db()

def load_config():
    if not os.path.exists(CONFIG_FILE): return {}
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        try: return json.load(f)
        except: return {}

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

@app.route('/')
def index():
    from flask import redirect
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    import glob
    videos_count = len(glob.glob(os.path.join(DATA_DIR, 'downloads', '*.*')))
    
    async def get_stats():
        async with async_session() as session:
            from sqlalchemy import select, func
            result = await session.execute(select(VideoAsset.status))
            rows = result.scalars().all()
            return rows

    rows = asyncio.run(get_stats())
    posted = sum(1 for r in rows if r == AssetStatus.DONE or r == AssetStatus.PUBLISHED or r == AssetStatus.SEEDED)
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
    """ Legacy route name, now returning DB data """
    async def fetch_all():
        async with async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(VideoAsset))
            assets = result.scalars().all()
            return [
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
    rows = asyncio.run(fetch_all())
    return jsonify({"rows": rows})

@app.route('/api/save-csv', methods=['POST'])
def save_assets():
    data = request.json
    updated_rows = data.get('rows', [])
    
    async def update_db():
        async with async_session() as session:
            from sqlalchemy import select
            for row in updated_rows:
                result = await session.execute(select(VideoAsset).where(VideoAsset.id == row['id']))
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
            await session.commit()

    asyncio.run(update_db())
    return jsonify({"success": True, "message": "Updated successfully"})

@app.route('/api/smart-sync', methods=['POST'])
def api_smart_sync():
    url = request.json.get('url')
    if not url: return jsonify({"error": "URL required"}), 400
    background_smart_sync_task(url)
    return jsonify({"success": True, "message": "Smart sync job dispatched to Huey."})

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
    
    # Reset external state for socket emit
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'w') as f:
            json.dump({"status": "running", "filename": filename, "logs": ["🚀 Deployment sequence initiated..."], "progress": 5}, f)
            
    socketio.emit('post_update', {"status": "running", "filename": filename, "logs": ["🚀 Deployment sequence initiated..."], "progress": 5})

    # Dispatch to Huey
    manual_post_task(filename, title, source_url, profile, transform, affiliate_link)
    
    return jsonify({"success": True, "message": "Triggered manual Selenium sequence via Huey."})

@app.route('/api/video/<filename>', methods=['DELETE'])
def delete_video(filename):
    async def delete_record():
        async with async_session() as session:
            from sqlalchemy import select, delete
            await session.execute(delete(VideoAsset).where(VideoAsset.filename == filename))
            await session.commit()
    asyncio.run(delete_record())
    
    video_path = os.path.join(DATA_DIR, 'downloads', filename)
    if os.path.exists(video_path): os.remove(video_path)
    return jsonify({"success": True})

# --- SSE / SocketIO Replacement for Polling ---
# A background thread reads the shared state JSON file and emits updates to connected clients.
def background_state_emitter():
    last_mtime = 0
    while True:
        try:
            if os.path.exists(STATE_FILE):
                mtime = os.path.getmtime(STATE_FILE)
                if mtime > last_mtime:
                    with open(STATE_FILE, 'r') as f:
                        state = json.load(f)
                    socketio.emit('post_update', state)
                    last_mtime = mtime
        except Exception as e: pass
        socketio.sleep(1)

@socketio.on('connect')
def test_connect():
    emit('my response', {'data': 'Connected to WebSockets for live logs'})

# Start the emitter thread
socketio.start_background_task(background_state_emitter)

# Account Routes
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

if __name__ == '__main__':
    # Initialize the AutoPostManager if needed or use Celery Beat / Huey Periodic Tasks
    # post_manager = scheduler.AutoPostManager(...) 
    socketio.run(app, host='0.0.0.0', debug=True, port=5001)
