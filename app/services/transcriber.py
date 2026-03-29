from faster_whisper import WhisperModel
import os

MODEL_SIZE = os.getenv("WHISPER_MODEL", "base")
_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path: str) -> list[dict]:
    model = get_model()
    segments, _ = model.transcribe(
        audio_path,
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
    )
    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                w = word.word.strip()
                if w:
                    words.append({
                        "text": w,
                        "start": round(word.start, 3),
                        "end": round(word.end, 3),
                    })
    return words


def group_into_phrases(words: list[dict], max_words: int = 3) -> list[dict]:
    """
    Groups words into display phrases (3 words max for readability).
    Each phrase end is extended to just before the next phrase starts
    so lyrics stay on screen longer.
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

    if chunk:
        phrases.append({
            "text": " ".join(w["text"] for w in chunk),
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
        })

    # Extend each phrase end to just before the next starts (fill gaps)
    for i in range(len(phrases) - 1):
        gap = phrases[i + 1]["start"] - phrases[i]["end"]
        if gap > 0:
            phrases[i]["end"] += min(gap * 0.8, 1.5)

    return phrases