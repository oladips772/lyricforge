"""
Stock footage fetcher.
Tries Pexels first, falls back to Pixabay.
Both are free with API keys.

Get keys:
  Pexels:  https://www.pexels.com/api/
  Pixabay: https://pixabay.com/api/docs/
"""

import os
import random
import requests
import urllib.request

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

TIMEOUT = 15


def _pexels_search(query: str, per_page: int = 5) -> list[str]:
    """Returns list of video URLs from Pexels."""
    if not PEXELS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": "portrait"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        urls = []
        for v in videos:
            # prefer HD file
            files = sorted(v.get("video_files", []), key=lambda f: f.get("height", 0), reverse=True)
            for f in files:
                if f.get("height", 0) >= 720:
                    urls.append(f["link"])
                    break
        return urls
    except Exception as e:
        print(f"[Pexels] Error: {e}")
        return []


def _pixabay_search(query: str, per_page: int = 5) -> list[str]:
    """Returns list of video URLs from Pixabay."""
    if not PIXABAY_API_KEY:
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "per_page": per_page,
                "video_type": "film",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        urls = []
        for h in hits:
            videos = h.get("videos", {})
            # prefer large > medium > small
            for size in ("large", "medium", "small"):
                v = videos.get(size, {})
                if v.get("url"):
                    urls.append(v["url"])
                    break
        return urls
    except Exception as e:
        print(f"[Pixabay] Error: {e}")
        return []


def fetch_clip(query: str, dest_path: str) -> bool:
    """
    Searches Pexels then Pixabay for `query`, downloads one clip to dest_path.
    Returns True on success.
    """
    urls = _pexels_search(query, per_page=5)
    if not urls:
        urls = _pixabay_search(query, per_page=5)

    if not urls:
        print(f"[footage] No results for: {query}")
        return False

    url = random.choice(urls)
    try:
        headers = {"User-Agent": "LyricForge/1.0"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"[footage] Download failed: {e}")
        return False


def fetch_clips_for_phrases(phrases: list[dict], mood_keywords: list[str], temp_dir: str) -> list[dict]:
    """
    For each phrase, search for a relevant clip.
    Falls back to mood keywords if phrase search fails.
    Returns phrases enriched with clip_path.
    """
    os.makedirs(temp_dir, exist_ok=True)
    seen_queries = set()
    enriched = []

    for i, phrase in enumerate(phrases):
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp4")

        # Try phrase text first (more specific)
        query = phrase["text"].strip()
        if not query or query in seen_queries:
            query = random.choice(mood_keywords)

        seen_queries.add(query)

        success = fetch_clip(query, clip_path)

        # Fallback to random mood keyword
        if not success:
            fallback = random.choice(mood_keywords)
            success = fetch_clip(fallback, clip_path)

        if success:
            enriched.append({**phrase, "clip_path": clip_path})
        else:
            # Skip phrase if no clip found (will be filled by neighbor in render)
            enriched.append({**phrase, "clip_path": None})
            print(f"[footage] Skipped phrase '{phrase['text']}' — no clip found")

    return enriched
