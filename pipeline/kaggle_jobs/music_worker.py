"""Runs on Kaggle. Generates score candidates with ACE-Step 1.5 in its own environment."""
import json
import os
import subprocess
import time
from pathlib import Path

JOB = json.loads(r'''@@JOB@@''')
OUT = Path("/kaggle/working")
START = time.time()


def sh(cmd):
    print("$", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


sh("pip install -q uv")
sh("git clone --depth 1 https://github.com/ACE-Step/ACE-Step-1.5 /tmp/ace")
sh("cd /tmp/ace && git rev-parse HEAD && uv sync -q --python 3.11")
Path("/tmp/ace/hs_run.py").write_text('''
import json, shutil, sys, time
from pathlib import Path
from acestep.handler import AceStepHandler
from acestep.llm_inference import LLMHandler
from acestep.inference import GenerationParams, GenerationConfig, generate_music
job = json.load(open("/tmp/job.json"))
out = Path("/kaggle/working")
def log(**r):
    open(out / "results.jsonl", "a").write(json.dumps(r) + "\\n"); print(r, flush=True)
t = time.time()
dit = AceStepHandler()
print(dit.initialize_service(project_root="/tmp/ace", config_path="acestep-v15-turbo", device="cuda"), flush=True)
llm = LLMHandler()
log(event="loaded", seconds=round(time.time() - t, 1))
for c in job["candidates"]:
    t = time.time()
    try:
        p = GenerationParams(task_type="text2music", caption=c["caption"], lyrics="[Instrumental]", instrumental=True, duration=c["duration_s"],
                             bpm=c["bpm"], keyscale=c["key"], seed=c["seed"], thinking=False, shift=3.0)
        r = generate_music(dit, llm, p, GenerationConfig(batch_size=1, audio_format="wav", use_random_seed=False, seeds=[c["seed"]]), save_dir="/tmp/gen%d" % c["seed"])
        if not r.success:
            raise RuntimeError(r.error)
        shutil.copy(r.audios[0]["path"], out / ("score_%d.wav" % c["seed"]))
        log(event="clip", item="score_%d" % c["seed"], key=c["cache_key"], status="ok", seconds=round(time.time() - t, 1))
    except Exception as e:
        log(event="clip", item="score_%d" % c["seed"], key=c["cache_key"], status="error", seconds=round(time.time() - t, 1), error=repr(e)[:500])
''')
Path("/tmp/job.json").write_text(json.dumps(JOB))
os.chdir("/tmp/ace")
sh("uv run --no-sync python hs_run.py")
with (OUT / "results.jsonl").open("a") as f:
    f.write(json.dumps({"event": "done", "seconds": round(time.time() - START, 1)}) + "\n")
