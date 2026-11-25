"""Runs on Kaggle. Draws pictures with FLUX.2 klein 4B, the same open model Cloudflare hosts, when its daily limit is used up."""
import json
import subprocess
import sys
import time
from pathlib import Path

JOB_ID = "@@JOB_ID@@"
OUT = Path("/kaggle/working")
START = time.time()
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "git+https://github.com/huggingface/diffusers.git", "transformers", "accelerate"], check=True)

import torch  # noqa: E402
from diffusers import Flux2KleinPipeline  # noqa: E402
from PIL import Image  # noqa: E402

job_file = next(p for p in Path("/kaggle/input").rglob("job.json") if json.loads(p.read_text())["job_id"] == JOB_ID)
job = json.loads(job_file.read_text())


def log(**row):
    with (OUT / "results.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(row, flush=True)


pipe = Flux2KleinPipeline.from_pretrained("black-forest-labs/FLUX.2-klein-4B", torch_dtype=torch.bfloat16)
pipe.enable_model_cpu_offload()  # a T4 cannot hold the text encoder and the image model together
log(event="loaded", seconds=round(time.time() - START, 1))
for c in job["pictures"]:
    t = time.time()
    try:
        refs = [Image.open(job_file.parent / f).convert("RGB") for f in c["files"]]
        image = pipe(prompt=c["prompt"], image=refs or None, width=c["size"][0], height=c["size"][1], guidance_scale=1.0, num_inference_steps=4,
                     generator=torch.Generator("cpu").manual_seed(c["seed"])).images[0]
        image.save(OUT / f"{c['item']}.png")
        log(event="picture", item=c["item"], key=c["key"], status="ok", seconds=round(time.time() - t, 1), peak_gb=round(torch.cuda.max_memory_allocated(0) / 1e9, 2))
    except Exception as e:
        log(event="picture", item=c["item"], key=c["key"], status="error", seconds=round(time.time() - t, 1), error=f"{type(e).__name__}: {e}"[:400])
    torch.cuda.empty_cache()
log(event="done", seconds=round(time.time() - START, 1))
