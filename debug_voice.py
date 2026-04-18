#!/usr/bin/env python3
"""
Voice diagnostic — run this to see what your mic picks up and what Whisper hears.
Usage: python debug_voice.py
"""
import sys
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice not installed"); sys.exit(1)

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("ERROR: faster-whisper not installed"); sys.exit(1)

SAMPLE_RATE = 16_000
DURATION    = 3.0

print("\n── Microphone devices ─────────────────────────────────────────")
devices = sd.query_devices()
default_in = sd.query_devices(kind='input')
print(f"Default input : {default_in['name']}")
for i, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        marker = " ◄ DEFAULT" if d['name'] == default_in['name'] else ""
        print(f"  [{i}] {d['name']}{marker}")

print("\n── Loading Whisper (base.en) ───────────────────────────────────")
model = WhisperModel("base.en", device="cpu", compute_type="int8")
print("Whisper ready.")

print("\n── 5 recording tests ──────────────────────────────────────────")
print("Say 'Jarvis' clearly each time when prompted.\n")

for i in range(5):
    input(f"  Test {i+1}/5 — press Enter then speak...")
    audio = sd.rec(int(SAMPLE_RATE * DURATION), samplerate=SAMPLE_RATE,
                   channels=1, dtype="float32")
    sd.wait()
    chunk = audio[:, 0]

    rms = float(np.sqrt(np.mean(chunk ** 2)))
    peak = float(np.max(np.abs(chunk)))

    segments, _ = model.transcribe(chunk, beam_size=5, language="en", vad_filter=False)
    text = " ".join(s.text.strip() for s in segments).strip()

    wake_words = {"jarvis", "travis", "j.a.r.v.i.s"}
    detected = any(w in text.lower() for w in wake_words)

    print(f"    RMS={rms:.4f}  Peak={peak:.4f}  Transcript='{text}'  Wake={'✓ YES' if detected else '✗ NO'}")

print("\n── Threshold diagnosis ────────────────────────────────────────")
print("Current ENERGY_THRESHOLD in voice_input.py: 0.008")
print("If your RMS values above are < 0.008, the mic is too quiet — lower the threshold.")
print("If Whisper didn't transcribe 'Jarvis', it may need vad_filter=False.\n")
