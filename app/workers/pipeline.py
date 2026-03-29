"""
Main pipeline worker.
Runs in background via FastAPI BackgroundTasks.
Steps: transcribe → detect mood → fetch footage → render → cleanup
"""

import os
import shutil
import traceback
from app.core.state import update_job
from app.services.transcriber import transcribe, group_into_phrases
from app.services.mood_detector import detect_mood
from app.services.footage import fetch_clips_for_phrases
from app.services.renderer import render_lyric_video, get_audio_duration


def run_pipeline(
    job_id: str,
    audio_path: str,
    style: str,
    text_style: str,
    resolution: str,
    output_dir: str,
    temp_dir: str,
):
    job_temp = os.path.join(temp_dir, job_id)
    os.makedirs(job_temp, exist_ok=True)
    output_path = os.path.join(output_dir, f"{job_id}.mp4")

    try:
        # ── Step 1: Transcribe ──────────────────────────────────
        update_job(job_id, status="transcribing", progress=10)
        print(f"[{job_id}] Transcribing...")
        words = transcribe(audio_path)

        if not words:
            # No speech detected — use mood keywords as visual-only video
            print(f"[{job_id}] No speech detected, generating visual-only video")
            words = []

        phrases = group_into_phrases(words, max_words=4)

        # ── Step 2: Detect mood ─────────────────────────────────
        update_job(job_id, status="detecting_mood", progress=25)
        print(f"[{job_id}] Detecting mood...")
        mood_data = detect_mood(audio_path)
        print(f"[{job_id}] Mood: {mood_data['mood']} | Tempo: {mood_data['tempo']} BPM")

        # If no lyrics, generate placeholder phrases from mood
        if not phrases:
            audio_dur = get_audio_duration(audio_path)
            interval = 4.0  # show each keyword every 4 seconds
            t = 0.0
            kw_cycle = mood_data["keywords"] * 10
            for i, kw in enumerate(kw_cycle):
                if t >= audio_dur:
                    break
                phrases.append({"text": "", "start": t, "end": min(t + interval, audio_dur)})
                t += interval

        # Override style if user passed "auto"
        if style == "auto":
            style = mood_data["mood"]

        # ── Step 3: Fetch footage ───────────────────────────────
        update_job(job_id, status="fetching_footage", progress=40)
        print(f"[{job_id}] Fetching stock footage for {len(phrases)} phrases...")

        enriched = fetch_clips_for_phrases(
            phrases=phrases,
            mood_keywords=mood_data["keywords"],
            temp_dir=job_temp,
        )

        # ── Step 4: Render ──────────────────────────────────────
        update_job(job_id, status="rendering", progress=70)
        print(f"[{job_id}] Rendering video...")

        render_lyric_video(
            phrases=enriched,
            audio_path=audio_path,
            output_path=output_path,
            text_style=text_style,
            resolution=resolution,
            temp_dir=job_temp,
        )

        # ── Step 5: Done ────────────────────────────────────────
        update_job(
            job_id,
            status="done",
            progress=100,
            url=f"/outputs/{job_id}.mp4",
            mood=mood_data["mood"],
            tempo=mood_data["tempo"],
            phrases_count=len(phrases),
        )
        print(f"[{job_id}] Done ✓ → {output_path}")

    except Exception as e:
        err = traceback.format_exc()
        print(f"[{job_id}] FAILED:\n{err}")
        update_job(job_id, status="failed", error=str(e), progress=0)

    finally:
        # Cleanup temp files
        try:
            shutil.rmtree(job_temp, ignore_errors=True)
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass
