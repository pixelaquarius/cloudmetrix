import traceback, sys
sys.stdout.reconfigure(encoding='utf-8')
from workers.tasks import background_smart_sync_task
from database.models import sync_session, VideoAsset

try:
    print("Running background_smart_sync_task.call_local('reviewcamoi')")
    background_smart_sync_task.call_local('reviewcamoi')
    print("Done! Let's check DB:")
    with sync_session() as session:
        assets = session.query(VideoAsset).all()
        for a in assets:
            print(a.filename, a.title)
except Exception as e:
    print("FAILED!!!")
    traceback.print_exc()
