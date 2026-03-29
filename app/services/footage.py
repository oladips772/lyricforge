"""
Stock footage fetcher — Pexels + Pixabay with fallback.
Fetches more clips (10-15) for better variety across the full video.
"""

import os
import random
import requests
import urllib.request

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
TIMEOUT = 15


def _pexels_search(query: str, per_page: int = 8) -> list[str]:
    if not PEXELS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "size": "medium"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        videos = r.json().get("videos", [])
        urls = []
        for v in videos:
            files = sorted(v.get("video_files", []), key=lambda f: f.get("height", 0), reverse=True)
            for f in files:
                if f.get("height", 0) >= 480:
                    urls.append(f["link"])
                    break
        return urls
    except Exception as e:
        print(f"[Pexels] {e}")
        return []


def _pixabay_search(query: str, per_page: int = 8) -> list[str]:
    if not PIXABAY_API_KEY:
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": PIXABAY_API_KEY, "q": query, "per_page": per_page, "video_type": "film"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        urls = []
        for h in hits:
            videos = h.get("videos", {})
            for size in ("large", "medium", "small"):
                v = videos.get(size, {})
                if v.get("url"):
                    urls.append(v["url"])
                    break
        return urls
    except Exception as e:
        print(f"[Pixabay] {e}")
        return []


def download_clip(url: str, dest_path: str) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LyricForge/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        # Verify file is not empty
        return os.path.getsize(dest_path) > 10000
    except Exception as e:
        print(f"[download] failed: {e}")
        return False


def fetch_clips_for_phrases(phrases: list[dict], mood_keywords: list[str], temp_dir: str) -> list[dict]:
    """
    Downloads a pool of clips based on mood keywords + lyric phrases.
    Targets 10-15 unique clips for variety across the full video.
    Returns phrases enriched with clip_path.
    """
    os.makedirs(temp_dir, exist_ok=True)

    # Build search queries: mood keywords first (guaranteed results), then lyric words
    search_queries = list(mood_keywords)  # 4 mood keywords

    # Add unique meaningful words from lyrics (skip short words)
    lyric_words = set()
    for p in phrases:
        for word in p["text"].split():
            if len(word) > 3 and word.lower() not in {"with", "that", "this", "they", "them", "from", "have", "been", "will", "would", "could", "should", "when", "what", "where", "which", "your", "their"}:
                lyric_words.add(word.lower())

    search_queries += list(lyric_words)[:6]  # up to 6 lyric-based queries

    # Fetch clips from all queries
    all_urls = []
    seen_urls = set()

    for query in search_queries:
        urls = _pexels_search(query, per_page=4)
        if not urls:
            urls = _pixabay_search(query, per_page=4)
        for url in urls:
            if url not in seen_urls:
                seen_urls.add(url)
                all_urls.append(url)

    if not all_urls:
        print("[footage] No URLs found — check API keys")

    # Download clips (target 12, stop when done)
    downloaded = []
    random.shuffle(all_urls)
    target = min(12, len(all_urls))

    for i, url in enumerate(all_urls[:target + 5]):  # try a few extras in case some fail
        if len(downloaded) >= target:
            break
        clip_path = os.path.join(temp_dir, f"clip_{i:04d}.mp4")
        print(f"[footage] Downloading clip {len(downloaded)+1}/{target}: {url[:60]}...")
        ok = download_clip(url, clip_path)
        if ok:
            downloaded.append(clip_path)

    print(f"[footage] Downloaded {len(downloaded)} clips")

    # Assign clips to phrases (round-robin)
    if not downloaded:
        # No clips — return phrases with None
        return [{**p, "clip_path": None} for p in phrases]

    enriched = []
    for i, phrase in enumerate(phrases):
        clip_path = downloaded[i % len(downloaded)]
        enriched.append({**phrase, "clip_path": clip_path})

    return enriched