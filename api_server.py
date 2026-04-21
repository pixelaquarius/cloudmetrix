import os
import threading
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from pyngrok import ngrok
from reup_engine import ReupEngine
from datetime import datetime

app = FastAPI(title="CloudMetrix Remote Engine")

# In-memory storage for status/logs
job_status = {
    "active": False,
    "last_run": None,
    "logs": []
}

class BatchRequest(BaseModel):
    tiktok_url: str
    asset_id: str = "105270308653797" # Default to Das Lab
    count: int = 10
    profile: str = "Automation_1"

def run_batch_job(request: BatchRequest):
    job_status["active"] = True
    job_status["last_run"] = datetime.now().isoformat()
    job_status["logs"].append(f"🚀 Started batch for {request.tiktok_url} at {job_status['last_run']}")
    
    try:
        engine = ReupEngine(profile=request.profile)
        results = engine.batch_process_channel(
            tiktok_url=request.tiktok_url,
            asset_id=request.asset_id,
            count=request.count
        )
        job_status["logs"].append(f"✅ Batch complete: {results['success']} Success, {results['failed']} Failed.")
    except Exception as e:
        job_status["logs"].append(f"❌ Batch Error: {str(e)}")
    finally:
        job_status["active"] = False

@app.get("/")
def read_root():
    return {"status": "CloudMetrix Engine Online", "active_job": job_status["active"]}

@app.post("/trigger")
def trigger_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    if job_status["active"]:
        return {"error": "A job is already running"}
    
    background_tasks.add_task(run_batch_job, request)
    return {"message": "Batch job triggered", "asset_id": request.asset_id}

@app.get("/status")
def get_status():
    return job_status

def start_ngrok():
    # Attempt to start ngrok
    try:
        # You can set an authtoken here if needed: ngrok.set_auth_token("YOUR_TOKEN")
        public_url = ngrok.connect(5001).public_url
        print(f"\n🌎 PUBLIC ENGINE URL: {public_url}")
        print(f"🔗 Trigger URL: {public_url}/trigger")
        print(f"📊 Status URL: {public_url}/status\n")
    except Exception as e:
        print(f"⚠️ Ngrok failed to start: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Start Ngrok in the background
    start_ngrok()
    
    # Run FastAPI
    uvicorn.run(app, host="0.0.0.0", port=5001)
