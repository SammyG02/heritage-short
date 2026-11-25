"""Runs on Kaggle. Last-resort Amharic voices with OmniVoice. No recording of a person is used.

The first line of each speaker is made without any reference; that synthetic line then keeps the speaker's voice the same for the rest.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

JOB = json.loads(r'''@@JOB@@''')
OUT = Path("/kaggle/working")
START = time.time()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "omnivoice", "soundfile"], check=True)

import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from omnivoice import OmniVoice, OmniVoiceGenerationConfig  # noqa: E402


def log(**row):
    with (OUT / "results.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(row, flush=True)


model = None
for name in (JOB["model"], "african-low-resource/omnivoice-amharic"):
    try:
        model = OmniVoice.from_pretrained(name, device_map="cuda:0", dtype=torch.float16)
        break
    except Exception as e:
        print(name, type(e).__name__, str(e)[:300], flush=True)
if model is None:
    raise SystemExit("no model could be loaded")
log(event="loaded", seconds=round(time.time() - START, 1), model=name)
keep = {}
for c in JOB["lines"]:
    t = time.time()
    try:
        torch.manual_seed(7)
        extra = {"voice_clone_prompt": keep[c["voice"]]} if c["voice"] in keep else {}
        audio = model.generate(text=c["text"], language="Amharic", generation_config=OmniVoiceGenerationConfig(num_step=32, guidance_scale=2.0), **extra)
        f = OUT / f"{c['item']}.wav"
        sf.write(str(f), audio[0], 24000, subtype="PCM_16")
        if c["voice"] not in keep:
            keep[c["voice"]] = model.create_voice_clone_prompt(ref_audio=str(f), ref_text=c["text"])
        log(event="line", item=c["item"], key=c["key"], status="ok", seconds=round(time.time() - t, 1))
    except Exception as e:
        log(event="line", item=c["item"], key=c["key"], status="error", seconds=round(time.time() - t, 1), error=f"{type(e).__name__}: {e}"[:400])
log(event="done", seconds=round(time.time() - START, 1))
