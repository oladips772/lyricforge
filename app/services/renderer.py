"""
FFmpeg rendering engine — fixed version.
- Covers full audio duration (no more 47s cutoffs)
- Proper glow using thick border + large shadows
- Clips loop if too short, rotated across all downloaded footage
- Footage switches every 6s for variety
"""

import os
import random
import subprocess
import json

TEXT_STYLES = {
    "bold": {
        "fontsize": 72,
        "fontcolor": "white",
        "box": 1,
        "boxcolor": "black@0.5",
        "boxborderw": 18,
        "font": "DejaVu-Sans-Bold",
        "shadowcolor": "black",
        "shadowx": 3,
        "shadowy": 3,
    },
    "minimal": {
        "fontsize": 64,
        "fontcolor": "white",
        "box": 0,
        "font": "DejaVu-Sans",
        "shadowcolor": "black",
        "shadowx": 3,
        "shadowy": 3,
    },
    "glow": {
        "fontsize": 72,
        "fontcolor": "FFD700",
        "box": 0,
        "font": "DejaVu-Sans-Bold",
        "borderw": 4,
        "bordercolor": "FF8C00",
        "shadowcolor": "FF4500",
        "shadowx": 8,
        "shadowy": 8,
    },
}

RESOLUTION_MAP = {
    "1080x1920": (1080, 1920),
    "1920x1080": (1920, 1080),
    "1080x1080": (1080, 1080),
}

CLIP_SWITCH_INTERVAL = 6.0


def get_video_duration(path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path
    ], capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 10.0))
    except Exception:
        return 10.0


def get_audio_duration(path: str) -> float:
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", path
    ], capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def build_drawtext(text: str, style_name: str) -> str:
    s = TEXT_STYLES.get(style_name, TEXT_STYLES["bold"])
    text = (text
        .replace("\\", "\\\\")
        .replace("'", "\u2019")
        .replace(":", "\\:")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
    )
    parts = [
        f"text='{text}'",
        f"fontsize={s['fontsize']}",
        f"fontcolor={s['fontcolor']}",
        f"font={s['font']}",
        "x=(w-text_w)/2",
        "y=(h*0.75-text_h/2)",
        f"shadowcolor={s['shadowcolor']}",
        f"shadowx={s['shadowx']}",
        f"shadowy={s['shadowy']}",
    ]
    if s.get("box"):
        parts += [f"box=1", f"boxcolor={s['boxcolor']}", f"boxborderw={s['boxborderw']}"]
    if s.get("borderw"):
        parts += [f"borderw={s['borderw']}", f"bordercolor={s['bordercolor']}"]
    return "drawtext=" + ":".join(parts)


def loop_clip_to_duration(clip_path: str, duration: float, out_path: str, w: int, h: int) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", clip_path,
        "-t", str(duration),
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30",
        "-an",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        out_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[loop_clip] failed: {result.stderr[-300:]}")
    return result.returncode == 0


def build_footage_timeline(phrases, available_clips, audio_dur, temp_dir, w, h):
    segments = []
    t = 0.0
    clip_idx = 0
    while t < audio_dur:
        seg_end = min(t + CLIP_SWITCH_INTERVAL, audio_dur)
        duration = round(seg_end - t, 3)
        clip_path = available_clips[clip_idx % len(available_clips)]
        clip_idx += 1
        mid = t + duration / 2
        active_text = ""
        for phrase in phrases:
            if phrase["start"] <= mid <= phrase["end"]:
                active_text = phrase["text"]
                break
        prepped = os.path.join(temp_dir, f"seg_{len(segments):04d}.mp4")
        ok = loop_clip_to_duration(clip_path, duration, prepped, w, h)
        if ok:
            segments.append({"start": t, "end": seg_end, "text": active_text, "prepped_path": prepped})
        else:
            print(f"[timeline] segment t={t:.1f}s failed")
        t = seg_end
    return segments


def render_lyric_video(phrases, audio_path, output_path, text_style="bold", resolution="1080x1920", temp_dir="temp"):
    w, h = RESOLUTION_MAP.get(resolution, (1080, 1920))
    audio_dur = get_audio_duration(audio_path)
    print(f"[render] Audio: {audio_dur:.1f}s | {w}x{h}")

    available_clips = list({
        p["clip_path"] for p in phrases
        if p.get("clip_path") and os.path.exists(p["clip_path"])
    })
    if not available_clips:
        raise RuntimeError("No valid clips — check API keys")

    random.shuffle(available_clips)
    print(f"[render] {len(available_clips)} clips available")

    segments = build_footage_timeline(phrases, available_clips, audio_dur, temp_dir, w, h)
    if not segments:
        raise RuntimeError("No segments built")
    print(f"[render] {len(segments)} segments covering {audio_dur:.1f}s")

    burned_paths = []
    segment_list_file = os.path.join(temp_dir, "segments.txt")

    for i, seg in enumerate(segments):
        burned = os.path.join(temp_dir, f"burned_{i:04d}.mp4")
        if seg["text"]:
            drawtext = build_drawtext(seg["text"], text_style)
            cmd = [
                "ffmpeg", "-y", "-i", seg["prepped_path"],
                "-vf", drawtext,
                "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-an", burned
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[render] drawtext failed seg {i}: {result.stderr[-200:]}")
                burned = seg["prepped_path"]
        else:
            burned = seg["prepped_path"]
        burned_paths.append(burned)

    with open(segment_list_file, "w") as f:
        for bp in burned_paths:
            f.write(f"file '{os.path.abspath(bp)}'\n")

    concat_video = os.path.join(temp_dir, "concat.mp4")
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", segment_list_file,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", concat_video
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed: {result.stderr[-400:]}")

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", concat_video,
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", str(audio_dur),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        output_path
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Audio mix failed: {result.stderr[-400:]}")

    final_dur = get_video_duration(output_path)
    print(f"[render] Final video: {final_dur:.1f}s ✓")
    return True