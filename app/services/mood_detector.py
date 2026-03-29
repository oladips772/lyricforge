"""
Mood detection service.
Uses librosa to extract audio features, then maps to mood/genre tags
for stock footage search queries.

Install: pip install librosa
"""

import librosa
import numpy as np


MOOD_MAP = {
    # (tempo_bucket, energy_bucket) -> (mood_label, search_keywords)
    ("fast", "high"):   ("energetic", ["neon city night", "crowd energy", "urban rush", "fire sparks"]),
    ("fast", "low"):    ("tense",     ["dark alley", "storm clouds", "lightning", "abandoned city"]),
    ("slow", "high"):   ("epic",      ["mountain peak", "ocean waves", "dramatic sky", "sunrise landscape"]),
    ("slow", "low"):    ("melancholic", ["rain window", "empty street", "foggy forest", "candle flame"]),
    ("medium", "high"): ("upbeat",   ["city lights", "rooftop sunset", "colorful abstract", "festival crowd"]),
    ("medium", "low"):  ("soulful",  ["studio smoke", "silhouette sunset", "jazz bar", "golden hour"]),
}


def detect_mood(audio_path: str) -> dict:
    """
    Analyzes audio and returns:
    {
      "mood": "energetic",
      "tempo": 128.4,
      "energy": 0.73,
      "keywords": ["neon city night", "crowd energy", ...]
    }
    """
    y, sr = librosa.load(audio_path, duration=60)  # analyze first 60s

    # Tempo
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    tempo = float(tempo)

    # RMS energy (loudness proxy)
    rms = float(np.mean(librosa.feature.rms(y=y)))
    # Normalize to 0-1 scale (typical range 0.01–0.3)
    energy_norm = min(rms / 0.15, 1.0)

    # Spectral centroid (brightness)
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))

    # Bucket
    if tempo < 85:
        tempo_bucket = "slow"
    elif tempo < 130:
        tempo_bucket = "medium"
    else:
        tempo_bucket = "fast"

    energy_bucket = "high" if energy_norm > 0.5 else "low"

    mood_label, keywords = MOOD_MAP.get(
        (tempo_bucket, energy_bucket),
        ("cinematic", ["aerial city", "abstract light", "golden bokeh", "cinematic landscape"])
    )

    return {
        "mood": mood_label,
        "tempo": round(tempo, 1),
        "energy": round(energy_norm, 3),
        "tempo_bucket": tempo_bucket,
        "energy_bucket": energy_bucket,
        "keywords": keywords,
    }
