from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uuid, os, shutil
from app.workers.pipeline import run_pipeline
from app.core.state import job_store

app = FastAPI(title="LyricForge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

TEMP_DIR = "temp"
OUTPUT_DIR = "outputs"
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


@app.post("/generate")
async def generate(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    style: str = "auto",         # auto | cinematic | urban | nature | abstract
    text_style: str = "bold",    # bold | minimal | glow
    resolution: str = "1080x1920"  # 1080x1920 (vertical) | 1920x1080 (horizontal)
):
    """
    Upload an audio file. LyricForge will:
    1. Transcribe lyrics with Whisper
    2. Detect mood/genre
    3. Fetch matching stock footage (Pexels + Pixabay)
    4. Render lyric video with FFmpeg
    5. Return download URL
    """
    allowed = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    ext = os.path.splitext(audio.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported format. Allowed: {allowed}")

    job_id = str(uuid.uuid4())
    audio_path = os.path.join(TEMP_DIR, f"{job_id}{ext}")

    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    job_store[job_id] = {"status": "queued", "progress": 0, "url": None, "error": None}

    background_tasks.add_task(
        run_pipeline,
        job_id=job_id,
        audio_path=audio_path,
        style=style,
        text_style=text_style,
        resolution=resolution,
        output_dir=OUTPUT_DIR,
        temp_dir=TEMP_DIR,
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/status/{job_id}")
def get_status(job_id: str):
    if job_id not in job_store:
        raise HTTPException(404, "Job not found")
    return {"job_id": job_id, **job_store[job_id]}


@app.get("/download/{job_id}")
def download(job_id: str):
    if job_id not in job_store:
        raise HTTPException(404, "Job not found")
    job = job_store[job_id]
    if job["status"] != "done":
        raise HTTPException(400, f"Job not ready. Status: {job['status']}")
    path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
    if not os.path.exists(path):
        raise HTTPException(404, "Output file missing")
    return FileResponse(path, media_type="video/mp4", filename=f"lyricforge_{job_id}.mp4")


@app.get("/health")
def health():
    return {"status": "ok", "service": "LyricForge"}
