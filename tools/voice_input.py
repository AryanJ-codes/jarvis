"""
Voice input — wake word detection + speech-to-text.

Wake word: Whisper-based local detection. Continuously transcribes 2-second
audio chunks and triggers when "jarvis" is heard. No account or API key needed.

STT: faster-whisper (local, CPU, Python 3.14 compatible).
Audio: sounddevice + numpy.
"""

from __future__ import annotations

import threading
from typing import Callable

import numpy as np

try:
    import sounddevice as sd  # type: ignore
    _SD_OK = True
except Exception:
    _SD_OK = False

try:
    from faster_whisper import WhisperModel  # type: ignore
    _WHISPER_OK = True
except ImportError:
    _WHISPER_OK = False

_whisper: "WhisperModel | None" = None
_SAMPLE_RATE = 16_000

# Words that count as the wake word (case-insensitive substring match)
_WAKE_WORDS = {"jarvis", "j.a.r.v.i.s", "travis", "jadwis", "jarves", "jarvis."}  # common Whisper misheard variants


def _get_whisper() -> "WhisperModel":
    global _whisper
    if _whisper is None:
        _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
    return _whisper


# ── Recording ─────────────────────────────────────────────────────────────────

def record_until_silence(
    silence_threshold: float = 0.015,
    silence_seconds: float = 1.5,
    max_seconds: float = 30.0,
    min_seconds: float = 0.4,
) -> "np.ndarray":
    """
    Record from the microphone until silence is detected.
    Returns a float32 numpy array at 16 kHz.
    """
    if not _SD_OK:
        raise RuntimeError("sounddevice not installed — run: pip install sounddevice")

    chunk_s = 0.1
    chunk_n = int(_SAMPLE_RATE * chunk_s)
    silence_limit = int(silence_seconds / chunk_s)
    min_chunks = int(min_seconds / chunk_s)
    max_chunks = int(max_seconds / chunk_s)

    chunks: list[np.ndarray] = []
    silent_streak = 0

    with sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="float32") as stream:
        for _ in range(max_chunks):
            frame, _ = stream.read(chunk_n)
            chunk = frame[:, 0]
            chunks.append(chunk)
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if rms < silence_threshold and len(chunks) > min_chunks:
                silent_streak += 1
                if silent_streak >= silence_limit:
                    break
            else:
                silent_streak = 0

    return np.concatenate(chunks) if chunks else np.zeros(chunk_n, dtype="float32")


def _record_chunk(seconds: float = 2.0) -> "np.ndarray":
    """Record a fixed-length audio chunk for wake word scanning."""
    n = int(_SAMPLE_RATE * seconds)
    audio = sd.rec(n, samplerate=_SAMPLE_RATE, channels=1, dtype="float32")
    sd.wait()
    return audio[:, 0]


# ── Transcription ─────────────────────────────────────────────────────────────

def transcribe(audio: "np.ndarray") -> str:
    """Transcribe a float32 numpy array (16 kHz mono) to text using Whisper."""
    if not _WHISPER_OK:
        raise RuntimeError("faster-whisper not installed — run: pip install faster-whisper")
    model = _get_whisper()
    segments, _ = model.transcribe(audio, beam_size=5, language="en", vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _contains_wake_word(text: str) -> bool:
    lower = text.lower()
    return any(w in lower for w in _WAKE_WORDS)


# ── Wake word ─────────────────────────────────────────────────────────────────

def wake_word_available() -> bool:
    """Always True — wake word uses local Whisper, no external service needed."""
    return _SD_OK and _WHISPER_OK


def listen_for_wake_word(
    on_detected: Callable[[], None],
    stop_event: "threading.Event | None" = None,
    # legacy param kept for API compatibility — ignored
    access_key: str = "",
) -> None:
    """
    Continuously scan audio in 2-second chunks using Whisper.
    Calls on_detected() when "Jarvis" is heard.
    Blocks until stop_event is set (or KeyboardInterrupt).

    Uses a tiny fast-path: only runs full Whisper if the chunk has
    enough energy (RMS > threshold), so the CPU stays quiet when silent.
    """
    if not _SD_OK:
        raise RuntimeError("sounddevice not installed — run: pip install sounddevice")
    if not _WHISPER_OK:
        raise RuntimeError("faster-whisper not installed — run: pip install faster-whisper")

    import queue as _queue

    stop   = stop_event or threading.Event()
    ENERGY = 0.005
    CHUNK  = int(_SAMPLE_RATE * 2.5)   # 2.5 s chunks

    audio_q: "_queue.Queue[np.ndarray]" = _queue.Queue()
    _buf: list[float] = []

    # Single persistent stream — mic stays open with one steady indicator dot,
    # no repeated open/close that causes the blinking orange light.
    def _cb(indata, frames, _t, _status):
        _buf.extend(indata[:, 0].tolist())
        while len(_buf) >= CHUNK:
            audio_q.put(np.array(_buf[:CHUNK], dtype="float32"))
            del _buf[:CHUNK]

    _get_whisper()  # warm up before stream opens

    proc_stop = threading.Event()

    def _processor():
        while not proc_stop.is_set():
            try:
                chunk = audio_q.get(timeout=1.0)
            except _queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(chunk ** 2)))
            if rms < ENERGY:
                continue
            try:
                segs, _ = _get_whisper().transcribe(
                    chunk, beam_size=3, language="en", vad_filter=False
                )
                text = " ".join(s.text.strip() for s in segs).strip()
                if text and _contains_wake_word(text):
                    on_detected()
                    stop.wait(timeout=0.5)  # cooldown to avoid double-trigger
            except Exception:
                pass

    threading.Thread(target=_processor, daemon=True).start()

    try:
        with sd.InputStream(
            samplerate=_SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=1024, callback=_cb,
        ):
            stop.wait()   # stream stays open until stop_event is set
    finally:
        proc_stop.set()
