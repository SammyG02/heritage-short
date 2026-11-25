"""Call each provider once and log the latency."""
import subprocess
import sys

from .core import config, providers, runlog

TEXT, TTS, IMAGE = "gemini-3.8-flash", "gemini-3.8-flash-tts", "@cf/black-forest-labs/flux-2-klein-4b"


def kaggle_quota():
    with runlog.call("smoke", "kaggle", "kaggle", "quota", {}) as rec:
        p = subprocess.run([sys.executable, "-m", "kaggle", "quota"], capture_output=True, text=True, timeout=90)
        if p.returncode:
            raise config.PipelineError((p.stdout + p.stderr)[-300:])
        rec["output"] = {"quota": " | ".join(" ".join(x.split()) for x in p.stdout.splitlines()[2:4])}


def run() -> int:
    tests = {
        "gemini text": lambda: providers.gemini_json("smoke", "text", 'Return the JSON {"ok": true}', TEXT),
        "gemini tts": lambda: providers.gemini_tts("smoke", "tts", "ሰላም", "Kore", "calm and warm", TTS),
        "cloudflare flux": lambda: providers.flux("smoke", "image", "a small clay coffee cup, soft painted light", 512, 512, 1, IMAGE),
        "kaggle": kaggle_quota,
    }
    failed = 0
    for name, fn in tests.items():
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {name}: {runlog.redact(str(e))[:400]}")
    return failed
