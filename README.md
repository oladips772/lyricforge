# 🎬 LyricForge

**Self-hosted lyric video generator API.**
Upload an audio file → get back a full lyric video with synced text over stock footage.

No manual lyrics needed. Whisper transcribes. Librosa detects mood. Pexels/Pixabay supply the visuals. FFmpeg renders it all.

---

## What it does

1. **Transcribes** your audio with OpenAI Whisper (runs locally, free)
2. **Detects mood/genre** from audio features (tempo, energy) using Librosa
3. **Fetches stock footage** from Pexels + Pixabay matching the mood
4. **Renders** a lyric video with FFmpeg — synced text burned over clips
5. **Returns a download URL** you can use anywhere

---

## Quick Start (Docker — recommended)

```bash
# 1. Clone / copy project to your VPS
git clone ... && cd lyricforge

# 2. Set your API keys
cp .env.example .env
nano .env   # add PEXELS_API_KEY and PIXABAY_API_KEY

# 3. Build and run
docker compose up -d --build

# 4. Test it
curl http://localhost:8010/health
```

First run downloads the Whisper model (~150MB for `base`). Subsequent starts are instant.

---

## Manual Setup (no Docker)

```bash
# System deps
sudo apt install ffmpeg fonts-dejavu-core libsndfile1

# Python deps
pip install -r requirements.txt

# Run
cp .env.example .env && nano .env
uvicorn app.main:app --host 0.0.0.0 --port 8010 --workers 2
```

---

## API Reference

### `POST /generate`

Upload an audio file and start a generation job.

**Form fields:**

| Field | Type | Default | Options |
|---|---|---|---|
| `audio` | file | required | `.mp3 .wav .m4a .ogg .flac` |
| `style` | string | `auto` | `auto cinematic urban nature abstract energetic melancholic` |
| `text_style` | string | `bold` | `bold minimal glow` |
| `resolution` | string | `1080x1920` | `1080x1920` (vertical) `1920x1080` (horizontal) `1080x1080` (square) |

**Example:**
```bash
curl -X POST http://your-server:8010/generate \
  -F "audio=@mysong.mp3" \
  -F "text_style=glow" \
  -F "resolution=1080x1920"
```

**Response:**
```json
{
  "job_id": "3f8a1c2d-...",
  "status": "queued"
}
```

---

### `GET /status/{job_id}`

Poll for job progress.

**Response (processing):**
```json
{
  "job_id": "3f8a1c2d-...",
  "status": "fetching_footage",
  "progress": 40,
  "url": null,
  "error": null
}
```

**Response (done):**
```json
{
  "job_id": "3f8a1c2d-...",
  "status": "done",
  "progress": 100,
  "url": "/outputs/3f8a1c2d-....mp4",
  "mood": "energetic",
  "tempo": 128.4,
  "phrases_count": 24
}
```

**Status values:** `queued → transcribing → detecting_mood → fetching_footage → rendering → done | failed`

---

### `GET /download/{job_id}`

Download the rendered MP4 directly.

```bash
curl -O http://your-server:8010/download/3f8a1c2d-...
```

---

### `GET /health`

Health check.

```json
{ "status": "ok", "service": "LyricForge" }
```

---

## n8n Integration

Use an **HTTP Request** node:

```
Method: POST
URL: http://your-server:8010/generate
Body: Form-Data
  - audio: [binary from previous node]
  - text_style: glow
  - resolution: 1080x1920
```

Then poll `/status/{{ $json.job_id }}` with a **Wait** node until `status == done`.

---

## API Keys (Free)

| Service | Limit | Get Key |
|---|---|---|
| Pexels | 200 req/hr | https://www.pexels.com/api/ |
| Pixabay | 5000 req/hr | https://pixabay.com/api/docs/ |

Both are completely free with no credit card required.

---

## Whisper Model Sizes

| Model | Size | Speed | Quality |
|---|---|---|---|
| `tiny` | 75MB | fastest | basic |
| `base` | 150MB | fast | good (default) |
| `small` | 500MB | medium | better |
| `medium` | 1.5GB | slower | great |
| `large-v3` | 3GB | slowest | best |

Set `WHISPER_MODEL=base` in `.env` for a good speed/quality balance on a VPS CPU.

---

## Project Structure

```
lyricforge/
├── app/
│   ├── main.py                 # FastAPI app + endpoints
│   ├── core/
│   │   └── state.py            # Job store (swap for Redis)
│   ├── services/
│   │   ├── transcriber.py      # Whisper transcription
│   │   ├── mood_detector.py    # Librosa mood analysis
│   │   ├── footage.py          # Pexels + Pixabay fetcher
│   │   └── renderer.py         # FFmpeg render engine
│   └── workers/
│       └── pipeline.py         # Orchestration pipeline
├── outputs/                    # Rendered videos (persisted)
├── temp/                       # Temp clips (auto-cleaned)
├── Dockerfile
├── docker-compose.yml
├── nginx.conf.example
├── requirements.txt
└── .env.example
```

---

## Typical Job Time

| Audio length | Approximate render time (CPU VPS) |
|---|---|
| 1 min | ~3–5 min |
| 3 min | ~8–15 min |
| 5 min | ~15–25 min |

Speed bottleneck is usually footage download. Use `WHISPER_MODEL=tiny` to shorten transcription on short clips.

---

## Upgrade Path

- **Redis job store** — replace `app/core/state.py` with Redis for persistence across restarts
- **Celery workers** — swap `BackgroundTasks` for Celery to handle concurrent jobs properly  
- **GPU transcription** — set `device="cuda"` in `transcriber.py` if your VPS has a GPU
- **Subtitle animation** — replace `drawtext` with ASS subtitle rendering for animated effects
- **Custom fonts** — drop `.ttf` files into `/static/fonts/` and reference in `renderer.py`
