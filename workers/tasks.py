import os
import asyncio
import time
import uuid
import random
import json
from datetime import datetime
from huey import crontab
from .huey_app import huey

from database.models import get_session, VideoAsset, AssetStatus, engine, async_session
from services.llm_service import llm_service
from video_transformer import VideoTransformer

# We use Flask-SocketIO via a separate emission script or generic POST_STATE.
# For simplicity in decoupled worker, we can push state to a shared JSON or emit directly if SocketIO message queue is setup.
# Here we'll just update the Database and a generic state file for Flask to read/emit.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

def update_post_state(status, filename, logs, progress=None):
    # Phase 5: Direct HTTP Emit to Flask Server to bypass File Locks
    state = {
        "status": status,
        "filename": filename,
        "logs": logs,
        "progress": progress
    }
    try:
        import requests
        requests.post('http://localhost:5001/api/internal/emit', json=state, timeout=2)
    except Exception as e:
        print(f"Failed to emit state: {e}")

@huey.task(retries=3, retry_delay=60)
def manual_post_task(filename, title, source_url, profile, transform, affiliate_link=None):
    """
    Background task to process and post a video to Facebook using JIT architecture.
    """
    import shutil
    try:
        import uploader # from root or core
        import downloader
        import playwright_uploader
        from database.models import sync_session
        
        # Sync DB Ops
        def fetch_record():
            with sync_session() as session:
                from sqlalchemy import select
                result = session.execute(select(VideoAsset).where(VideoAsset.filename == filename))
                return result.scalar_one_or_none()

        record = fetch_record()
        
        working_filename = filename
        
        # JIT Download to /tmp/ directory
        tmp_dir = os.path.join(DATA_DIR, 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        working_path = os.path.abspath(os.path.join(tmp_dir, working_filename))
        
        try:
            if source_url:
                update_post_state('running', working_filename, [f"JIT Engine: Fetching media from {source_url}..."])
                success = downloader.download_video_jit(source_url, working_path)
                if not success:
                    raise Exception("JIT Media extraction failed!")
            
            if not os.path.exists(working_path):
                raise Exception(f"Media file not found at: {working_path}")
                
            # Transformation
            if transform:
                update_post_state('running', working_filename, ["🛡️ Applying Video Filters (Flip, Crop, Speed, Branding)..."], 30)
                transformed_filename = "bypass_" + working_filename
                transformed_path = os.path.abspath(os.path.join(tmp_dir, transformed_filename))
                
                transformer = VideoTransformer()
                # Run async transformer in sync worker
                trans_success = asyncio.run(transformer.apply_bypass_filters(working_path, transformed_path))
                
                if trans_success:
                    update_post_state('running', working_filename, ["✅ Transformation complete!"], 60)
                    working_path = transformed_path
                    working_filename = transformed_filename

            # A/B Testing Caption Selection
            caption_to_use = title
            used_group = "A"
            if record and record.caption_variations:
                try:
                    variations = json.loads(record.caption_variations)
                    if variations:
                        index = random.randint(0, len(variations) - 1)
                        caption_to_use = variations[index]
                        used_group = f"Var_{index+1}"
                except: pass

            # External State for Growth Hooks
            ext_state = {
                "status": "running",
                "filename": working_filename,
                "logs": [],
                "affiliate_link": affiliate_link
            }

            # Upload
            success = playwright_uploader.upload_to_facebook_page_playwright(
                working_path, 
                caption_to_use, 
                profile_name=profile,
                external_state=ext_state
            )
            
            def update_db_status(new_status, new_filename=None, group=None):
                with sync_session() as session:
                    from sqlalchemy import select
                    result = session.execute(select(VideoAsset).where(VideoAsset.filename == filename))
                    rec = result.scalar_one_or_none()
                    if rec:
                        rec.status = new_status
                        if new_filename: rec.filename = new_filename
                        if group: rec.ab_test_group = group
                        session.commit()

            if success:
                update_db_status(AssetStatus.DONE, working_filename, used_group)
                update_post_state('idle', working_filename, ["🎉 JIT POST COMPLETED!"], 100)
            else:
                update_db_status(AssetStatus.FAILED, working_filename)
                update_post_state('idle', working_filename, ["❌ Upload failed. Please check logs."])
                raise Exception("Upload Sequence Failed") # Trigger Retry

        finally:
            # PHASE 4: Self-Clean
            if os.path.exists(working_path):
                try:
                    os.remove(working_path)
                    print(f"🧹 Self-Clean: Deleted temporary file {working_path}")
                except Exception as e:
                    print(f"Failed to delete tmp file: {e}")

    except Exception as e:
        print(f"CRITICAL ENGINE ERROR: {e}")
        def fail_db_status():
            from database.models import sync_session
            with sync_session() as session:
                from sqlalchemy import select
                result = session.execute(select(VideoAsset).where(VideoAsset.filename == filename))
                rec = result.scalar_one_or_none()
                if rec:
                    rec.status = AssetStatus.FAILED
                    session.commit()
        fail_db_status()
        raise e

@huey.task()
def background_smart_sync_task(url_or_id):
    import downloader
    from interceptor_downloader import TikTokSmartDownloader
    from database.models import sync_session
    import uuid
    
    url_or_id = str(url_or_id).strip()
    
    # 1. Formatting
    is_profile = False
    if url_or_id.startswith("http"):
        url = url_or_id
        if "/video/" not in url:
            is_profile = True
    else:
        # User threw an ID. If it's pure digits, it might be a video ID, but usually they mean a username
        if url_or_id.isdigit():
            # Very rare, just use TikWM API directly for video ID
            url = f"https://www.tiktok.com/@user/video/{url_or_id}" 
        else:
            uid = url_or_id if url_or_id.startswith("@") else f"@{url_or_id}"
            url = f"https://www.tiktok.com/{uid}"
            is_profile = True

    update_post_state('running', "Discovery", [f"🔍 JIT Discovery Started for: {url}"])

    if is_profile:
        # --- PROFILE SYNC (Batch) ---
        update_post_state('running', "Discovery", ["📚 Profile detected. Running batch scrape..."])
        
        # We use a generator, so we iterate through it
        records = downloader.sync_tiktok(url, max_videos=10) # Limit to 10 for safety
        
        saved_count = 0
        with sync_session() as session:
            for rec in records:
                # Generate AI Variations
                variations = []
                try:
                    import asyncio
                    import json
                    from services.gemini_service import CloudMetrixLLMService
                    llm_svc = CloudMetrixLLMService()
                    async def fetch_caps():
                        return await llm_svc.generate_caption_variations(rec["title"], "")
                    variations = asyncio.run(fetch_caps())
                except Exception as e:
                    print(f"LLM Error: {e}")

                new_asset = VideoAsset(
                    id=str(uuid.uuid4())[:8],
                    filename=rec["filename"],
                    title=rec["title"],
                    caption="",
                    source_url=rec["source_url"],
                    thumbnail_path=rec["thumbnail_path"],
                    caption_variations=json.dumps(variations),
                    status=AssetStatus.PENDING
                )
                session.add(new_asset)
                saved_count += 1
                update_post_state('running', "Discovery", [f"✅ Added {rec['filename']} to Queue."])
            
            if saved_count > 0:
                session.commit()
        update_post_state('idle', "Discovery", [f"🎉 Profile Sync Complete! Found {saved_count} videos."], 100)
        
    else:
        # --- SINGLE VIDEO SYNC ---
        update_post_state('running', "Discovery", ["🎥 Single Video detected. Extracting stream..."])
        downloader_obj = TikTokSmartDownloader(headless=True)
        
        async def run_sync():
            v_url, meta = await downloader_obj.fetch_media_and_metadata(url)
            if v_url:
                timestamp = int(time.time())
                filename = f"smart_{timestamp}.mp4"
                
                # Generate AI Variations
                variations = []
                try:
                    variations = await llm_service.generate_caption_variations(
                        meta.get('title', 'Smart Asset'), 
                        meta.get('description', '')
                    )
                except: pass
                
                # Add to DB
                with sync_session() as session:
                    new_asset = VideoAsset(
                        id=str(uuid.uuid4())[:8],
                        filename=filename,
                        title=meta.get('title', 'Smart Asset'),
                        caption=meta.get('description', ''),
                        source_url=v_url,
                        thumbnail_path=meta.get('thumbnail_path', ''),
                        caption_variations=json.dumps(variations),
                        status=AssetStatus.PENDING
                    )
                    session.add(new_asset)
                    session.commit()
                update_post_state('idle', "Discovery", ["✅ Smart Sync complete! Asset added to queue."], 100)
            else:
                update_post_state('idle', "Discovery", ["❌ Interceptor failed to catch stream."])

        asyncio.run(run_sync())

# --- PHASE 3: Cronjob Scheduler ---
@huey.periodic_task(crontab(minute='*'))
def check_scheduled_posts():
    """
    Runs every minute to check if any VideoAsset is scheduled to post now.
    """
    from database.models import sync_session
    from sqlalchemy import select
    
    with sync_session() as session:
        now = datetime.utcnow()
        # Find all assets that are scheduled and the scheduled_time has passed
        result = session.execute(
            select(VideoAsset).where(
                VideoAsset.status == AssetStatus.SCHEDULED,
                VideoAsset.scheduled_time <= now
            )
        )
        assets = result.scalars().all()
        
        for asset in assets:
            print(f"⏰ [Cronjob] Found scheduled post: {asset.filename} (Time: {asset.scheduled_time})")
            
            # Change status to processing to avoid duplicate dispatches
            asset.status = AssetStatus.PENDING 
            
            # Dispatch to Huey execution task
            # JIT Download will happen inside manual_post_task (Phase 4)
            transform = asset.bypass_copyright == '1'
            manual_post_task(
                filename=asset.filename,
                title=asset.title,
                source_url=asset.source_url,
                profile=asset.profile,
                transform=transform,
                affiliate_link=asset.affiliate_link
            )
        
        if assets:
            session.commit()

