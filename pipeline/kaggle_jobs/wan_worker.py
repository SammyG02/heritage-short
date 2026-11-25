"""Runs on Kaggle (2x T4). Animates keyframes with Wan 2.2 TI2V-5B, saving each clip as it finishes."""
import gc
import json
import subprocess
import sys
import time
from pathlib import Path

JOB_ID = "@@JOB_ID@@"
OUT = Path("/kaggle/working")
START = time.time()

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers", "ftfy", "imageio", "imageio-ffmpeg", "accelerate"], check=True)

import torch  # noqa: E402
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline  # noqa: E402
from diffusers.utils import export_to_video  # noqa: E402
from PIL import Image, ImageOps  # noqa: E402

job_file = next(p for p in Path("/kaggle/input").rglob("job.json") if json.loads(p.read_text())["job_id"] == JOB_ID)
job = json.loads(job_file.read_text())
model = job["model"]
second = "cuda:1" if torch.cuda.device_count() > 1 else "cuda:0"
print("GPUs", torch.cuda.device_count(), torch.cuda.get_device_name(0), "torch", torch.__version__, flush=True)


def log(**row):
    with (OUT / "results.jsonl").open("a") as f:
        f.write(json.dumps(row) + "\n")
    print(row, flush=True)


# The text encoder is the largest part: use it once, then free it before loading the video model.
enc = WanImageToVideoPipeline.from_pretrained(model, transformer=None, vae=None, torch_dtype=torch.bfloat16).to(second)
embeds = {}
with torch.no_grad():
    for prompt in {j["motion_prompt"] for j in job["clips"]}:
        pos, neg = enc.encode_prompt(prompt=prompt, negative_prompt=job["negative_prompt"], do_classifier_free_guidance=True, device=second)
        embeds[prompt] = (pos.cpu(), neg.cpu())
del enc
gc.collect()
torch.cuda.empty_cache()

vae = AutoencoderKLWan.from_pretrained(model, subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(model, vae=vae, text_encoder=None, tokenizer=None, torch_dtype=torch.float16).to("cuda:0")
decoder = AutoencoderKLWan.from_pretrained(model, subfolder="vae", torch_dtype=torch.float32).to(second)
decoder.enable_tiling()
log(event="loaded", seconds=round(time.time() - START, 1))

for j in job["clips"]:
    t0 = time.time()
    try:
        w, h = j["size"]
        image = ImageOps.fit(Image.open(job_file.parent / j["keyframe_file"]).convert("RGB"), (w, h), Image.LANCZOS)
        pos, neg = embeds[j["motion_prompt"]]
        with torch.no_grad():
            latents = pipe(image=image, prompt_embeds=pos.to("cuda:0", torch.float16), negative_prompt_embeds=neg.to("cuda:0", torch.float16),
                           height=h, width=w, num_frames=job["frames"], num_inference_steps=job["steps"],
                           guidance_scale=job["guidance"], generator=torch.Generator("cpu").manual_seed(j["seed"]),
                           output_type="latent").frames
            denoise = time.time() - t0
            if not torch.isfinite(latents).all():
                raise RuntimeError("latents contain NaN in fp16")
            torch.cuda.empty_cache()
            z = latents.to(second, torch.float32)
            mean = torch.tensor(decoder.config.latents_mean).view(1, -1, 1, 1, 1).to(z)
            std = torch.tensor(decoder.config.latents_std).view(1, -1, 1, 1, 1).to(z)
            video = decoder.decode(z * std + mean, return_dict=False)[0]
        frames = pipe.video_processor.postprocess_video(video.cpu(), output_type="np")[0]
        export_to_video(frames, str(OUT / f"{j['item']}.mp4"), fps=24, quality=9)
        log(event="clip", item=j["item"], key=j["key"], status="ok", seconds=round(time.time() - t0, 1), denoise_s=round(denoise, 1),
            peak_gb=round(torch.cuda.max_memory_allocated(0) / 1e9, 2))
    except Exception as e:
        log(event="clip", item=j["item"], key=j["key"], status="error", seconds=round(time.time() - t0, 1), error=f"{type(e).__name__}: {e}"[:500])
    gc.collect()
    torch.cuda.empty_cache()
log(event="done", seconds=round(time.time() - START, 1))
