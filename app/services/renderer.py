"""
FFmpeg rendering engine.
Trims each clip to phrase duration, burns lyric text, concatenates, mixes audio.
"""

import os
import subprocess
import json
import math
from pathlib import Path

# Text style presets
TEXT_STYLES = {
    "bold": {
        "fontsize": 72,
        "fontcolor": "white",
        "box": 1,
        "boxcolor": "black@0.45",
        "boxborderw": 16,
        "font": "DejaVu-Sans-Bold",
        "shadowcolor": "black@0.8",
        "shadowx": 3,
        "shadowy": 3,
    },
    "minimal": {
        "fontsize": 60,
        "fontcolor": "white",
        "box": 0,
        "font": "DejaVu-Sans",
        "shadowcolor": "black@0.9",
        "shadowx": 2,
        "shadowy": 2,
    },
    "glow": {
        "fontsize": 68,
        "fontcolor": "#FFD700",
        "box": 0,
        "font": "DejaVu-Sans-Bold",
        "shadowcolor": "#FF8C00@0.8",
        "shadowx": 0,
        "shadowy": 0,
        "borderw": 3,
        "bordercolor": "#FF8C00",
    },
}

RESOLUTION_MAP = {
    "1080x1920": (1080, 1920),  # vertical / Shorts
    "1920x1080": (1920, 1080),  # horizontal / YouTube
    "1080x1080": (1080, 1080),  # square / Instagram
}


def get_video_duration(path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", path
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            return float(s.get("duration", 10.0))
    return 10.0


def get_audio_duration(path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "a", path
    ], capture_output=True, text=True)
    data = json.loads(result.stdout)
    for s in data.get("streams", []):
        return float(s.get("duration", 0))
    return 0.0


def build_drawtext(text: str, style_name: str, w: int, h: int) -> str:
    """Build FFmpeg drawtext filter string."""
    s = TEXT_STYLES.get(style_name, TEXT_STYLES["bold"])

    # Escape special chars for FFmpeg
    text = text.replace("'", "\\'").replace(":", "\\:").replace("\\", "\\\\")

    parts = [
        f"text='{text}'",
        f"fontsize={s['fontsize']}",
        f"fontcolor={s['fontcolor']}",
        f"font={s['font']}",
        f"x=(w-text_w)/2",
        f"y=(h*0.72)",  # lower third area
        f"shadowcolor={s.get('shadowcolor', 'black@0.8')}",
        f"shadowx={s.get('shadowx', 2)}",
        f"shadowy={s.get('shadowy', 2)}",
    ]

    if s.get("box"):
        parts += [
            f"box={s['box']}",
            f"boxcolor={s['boxcolor']}",
            f"boxborderw={s['boxborderw']}",
        ]

    if s.get("borderw"):
        parts += [
            f"borderw={s['borderw']}",
            f"bordercolor={s['bordercolor']}",
        ]

    return "drawtext=" + ":".join(parts)


def trim_and_prep_clip(clip_path: str, duration: float, out_path: str, w: int, h: int) -> bool:
    """
    Trims clip to `duration` seconds and scales/crops to target resolution.
    Returns True on success.
    """
    vid_duration = get_video_duration(clip_path)
    # Start at random offset if clip is longer than needed
    max_start = max(0, vid_duration - duration - 0.5)
    import random
    start = round(random.uniform(0, max_start), 2) if max_start > 0 else 0

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", clip_path,
        "-t", str(duration),
        "-vf", (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},"
            f"setsar=1"
        ),
        "-r", "30",
        "-an",  # strip audio from clip
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        out_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def render_lyric_video(
    phrases: list[dict],
    audio_path: str,
    output_path: str,
    text_style: str = "bold",
    resolution: str = "1080x1920",
    temp_dir: str = "temp",
) -> bool:
    """
    Full render pipeline:
    1. Trim each clip to phrase duration
    2. Burn lyrics with drawtext
    3. Concatenate all segments
    4. Mix with original audio
    """
    w, h = RESOLUTION_MAP.get(resolution, (1080, 1920))
    audio_dur = get_audio_duration(audio_path)

    # Fill in None clip_paths with neighbor
    last_good = None
    for p in phrases:
        if p.get("clip_path") and os.path.exists(p["clip_path"]):
            last_good = p["clip_path"]
        elif last_good:
            p["clip_path"] = last_good

    # Filter out phrases still missing clips
    valid_phrases = [p for p in phrases if p.get("clip_path") and os.path.exists(p["clip_path"])]

    if not valid_phrases:
        raise RuntimeError("No valid clips found — check API keys and network")

    # Extend last phrase to cover full audio duration
    valid_phrases[-1]["end"] = max(valid_phrases[-1]["end"], audio_dur)

    segment_paths = []
    segment_list_file = os.path.join(temp_dir, "segments.txt")

    for i, phrase in enumerate(valid_phrases):
        duration = max(0.5, phrase["end"] - phrase["start"])
        prepped = os.path.join(temp_dir, f"prepped_{i:04d}.mp4")
        burned = os.path.join(temp_dir, f"burned_{i:04d}.mp4")

        # Step 1: trim + scale
        ok = trim_and_prep_clip(phrase["clip_path"], duration, prepped, w, h)
        if not ok:
            print(f"[render] trim failed for phrase {i}, skipping")
            continue

        # Step 2: burn lyrics
        drawtext = build_drawtext(phrase["text"], text_style, w, h)
        cmd = [
            "ffmpeg", "-y",
            "-i", prepped,
            "-vf", drawtext,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-an",
            burned
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[render] drawtext failed for phrase {i}: {result.stderr[-300:]}")
            continue

        segment_paths.append(burned)

    if not segment_paths:
        raise RuntimeError("All segment renders failed")

    # Step 3: write concat list
    with open(segment_list_file, "w") as f:
        for sp in segment_paths:
            f.write(f"file '{os.path.abspath(sp)}'\n")

    # Step 4: concat + add audio
    concat_video = os.path.join(temp_dir, "concat.mp4")
    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", segment_list_file,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "22",
        concat_video
    ]
    result = subprocess.run(cmd_concat, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed: {result.stderr[-500:]}")

    # Step 5: mix audio (trim video to audio length)
    cmd_mix = [
        "ffmpeg", "-y",
        "-i", concat_video,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-t", str(audio_dur),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    result = subprocess.run(cmd_mix, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio mix failed: {result.stderr[-500:]}")

    return True
