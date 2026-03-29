"""
Transcription service using faster-whisper (local, free, no API key).
Install: pip install faster-whisper
Model downloads automatically on first run (~150MB for 'base', ~1.5GB for 'large-v3').
"""

from faster_whisper import WhisperModel
import os

# Use 'base' for speed, 'medium' for accuracy, 'large-v3' for best quality
# device='cpu' works fine; set to 'cuda' if you have a GPU on VPS
MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path: str) -> list[dict]:
    """
    Returns list of word-level segments:
    [
      {"text": "fire", "start": 0.82, "end": 1.10},
      {"text": "in", "start": 1.10, "end": 1.22},
      ...
    ]
    """
    model = get_model()
    segments, _ = model.transcribe(
        audio_path,
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,  # skip silence
    )

    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                words.append({
                    "text": word.word.strip(),
                    "start": round(word.start, 3),
                    "end": round(word.end, 3),
                })

    return words


def group_into_phrases(words: list[dict], max_words: int = 4) -> list[dict]:
    """
    Groups words into display phrases (max N words per line).
    Returns:
    [
      {"text": "fire in the night", "start": 0.82, "end": 2.10},
      ...
    ]
    """
    if not words:
        return []

    phrases = []
    chunk = []

    for word in words:
        chunk.append(word)
        if len(chunk) >= max_words:
            phrases.append({
                "text": " ".join(w["text"] for w in chunk),
                "start": chunk[0]["start"],
                "end": chunk[-1]["end"],
            })
            chunk = []

    # flush remaining words
    if chunk:
        phrases.append({
            "text": " ".join(w["text"] for w in chunk),
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
        })

    return phrases
