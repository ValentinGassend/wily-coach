"""The microphone track of the user's screen recordings (rush/*.mp4, audio track 1: his voice), transcribed with its
times (French, faster-whisper large-v2 on the CPU): his spoken feedback on the training. One .txt per recording in
out/rush_tx, the ones done already skipped.

    python tools/transcribe_rush.py [names...]      the latest recording by default"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402

RUSH = os.path.join(HERE, "rush")
OUT = os.path.join(config.OUT, "rush_tx")
PROMPT = ("Counter-Strike 2, entraînement, Wily, bots, smoke, flash, molotov, rush, site A, site B, mid, prefire, crossfire, "
          "momentum, warmup, setup, lineup, jumpthrow, KZ.")


def main():
    config.low_priority()
    os.makedirs(OUT, exist_ok=True)
    names = sys.argv[1:] or sorted((f[:-4] for f in os.listdir(RUSH) if f.endswith(".mp4")), reverse=True)[:1]
    from faster_whisper import WhisperModel
    model = WhisperModel("large-v2", device="cpu", compute_type="int8", cpu_threads=8)
    for name in names:
        txt = os.path.join(OUT, name + ".txt")
        if os.path.exists(txt) and os.path.getsize(txt) > 0:
            continue
        wav = os.path.join(OUT, name + ".wav")
        if not os.path.exists(wav):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(RUSH, name + ".mp4"), "-map", "0:a:1", "-ac", "1", "-ar", "16000", wav],
                           check=True)
        t = time.time()
        segs, _ = model.transcribe(wav, language="fr", vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}, beam_size=5,
                                   initial_prompt=PROMPT)
        with open(txt + ".part", "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"[{int(s.start // 60):02d}:{s.start % 60:04.1f}] {s.text.strip()}\n")
        os.replace(txt + ".part", txt)
        print(name, f"{time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
