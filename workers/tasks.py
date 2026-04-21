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
    # This acts as a bridge between Huey workers and the main Flask app.
    # A robust way is storing this in Redis or SQLite. We'll use a fast JSON dump for this MVP.
    state_file = os.path.join(DATA_DIR, 'post_state.json')
    state = {
        "status": status,
        "filename": filename,
        "logs": logs,
        "progress": progress
    }
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f)

@huey.task(retries=3, retry_delay=60)
def manual_post_task(filename, title, source_url, profile, transform, affiliate_link=None):
    """
    Background task to process and post a video to Facebook.
    Retry up to 3 times with 60s delay if network/auth fails.
    """
    try:
        import uploader # from root or core
        import downloader
        import playwright_uploader
        
        # Async DB Ops in Sync Huey Worker
        async def fetch_record():
            async with async_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(VideoAsset).where(VideoAsset.filename == filename))
                return result.scalar_one_or_none()

        record = asyncio.run(fetch_record())
        
        working_filename = filename
        working_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', working_filename))
        
        # JIT Download
        is_legacy = any(working_filename.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.wav'])
        if is_legacy:
            working_filename = os.path.splitext(working_filename)[0] + ".mp4"
            working_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', working_filename))

        if (not os.path.exists(working_path) or is_legacy) and source_url:
            update_post_state('running', working_filename, [f"JIT Engine: Fetching target media from {source_url}..."])
            success = downloader.download_video_jit(source_url, working_path)
            if not success:
                raise Exception("JIT Media extraction failed!")
        
        if not os.path.exists(working_path):
            raise Exception(f"Media file not found at: {working_path}")
            
        # Transformation
        if transform:
            update_post_state('running', working_filename, ["🛡️ Applying Video Filters (Flip, Crop, Speed, Branding)..."], 30)
            transformed_filename = "bypass_" + working_filename
            transformed_path = os.path.abspath(os.path.join(DATA_DIR, 'downloads', transformed_filename))
            
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
                    # Simple Random A/B test
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
        
        async def update_db_status(new_status, new_filename=None, group=None):
            async with async_session() as session:
                from sqlalchemy import select
                result = await session.execute(select(VideoAsset).where(VideoAsset.filename == filename))
                rec = result.scalar_one_or_none()
                if rec:
                    rec.status = new_status
                    if new_filename: rec.filename = new_filename
                    if group: rec.ab_test_group = group
                    await session.commit()

        if success:
            asyncio.run(update_db_status(AssetStatus.DONE, working_filename, used_group))
            update_post_state('idle', working_filename, ["🎉 MANUAL POST COMPLETED!"], 100)
        else:
            asyncio.run(update_db_status(AssetStatus.FAILED, working_filename))
            update_post_state('idle', working_filename, ["❌ Upload failed. Please check logs."])
            raise Exception("Upload Sequence Failed") # Trigger Retry

    except Exception as e:
        print(f"CRITICAL ENGINE ERROR: {e}")
        asyncio.run(update_db_status(AssetStatus.FAILED, filename))
        raise e # Let Huey handle retry

@huey.task()
def background_smart_sync_task(url):
    import downloader
    from interceptor_downloader import TikTokSmartDownloader
    
    downloader_obj = TikTokSmartDownloader(headless=True)
    
    async def run_sync():
        v_url, meta = await downloader_obj.fetch_media_and_metadata(url)
        if v_url:
            timestamp = int(time.time())
            filename = f"smart_{timestamp}.mp4"
            save_path = os.path.join(DATA_DIR, 'downloads', filename)
            
            if downloader_obj.download_file(v_url, save_path):
                # Generate AI Variations
                variations = await llm_service.generate_caption_variations(
                    meta.get('title', 'Smart Asset'), 
                    meta.get('description', '')
                )
                
                # Add to DB
                async with async_session() as session:
                    new_asset = VideoAsset(
                        id=str(uuid.uuid4())[:8],
                        filename=filename,
                        title=meta.get('title', 'Smart Asset'),
                        caption=meta.get('description', ''),
                        source_url=url,
                        caption_variations=json.dumps(variations)
                    )
                    session.add(new_asset)
                    await session.commit()
                print("✅ Smart Sync complete! Asset added to queue.")
            else:
                print("❌ Download failed in Smart Sync.")
        else:
            print("❌ Interceptor failed to catch stream.")

    asyncio.run(run_sync())
