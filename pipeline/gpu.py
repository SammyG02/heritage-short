"""Kaggle jobs: submit stale GPU work, check it, and fetch finished outputs into the cache."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from PIL import Image

from . import keyframes, music, shots
from .core import cache, config, runlog
from .core.storyboard import out, require_consent

WORKERS = Path(__file__).parent / "kaggle_jobs"
DATASET = "heritage-short-jobs"


def kaggle(*args, check=True, timeout=600):
    p = subprocess.run([sys.executable, "-X", "utf8", "-m", "kaggle", *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    text = runlog.redact(p.stdout + p.stderr)
    if check and (p.returncode or "error" in text.lower()):
        raise config.PipelineError("Kaggle: " + text[-600:])
    return text


def user():
    return config.secret("KAGGLE_USERNAME")


def _state(sb, kind):
    return out(sb, "jobs", f"{kind}.json")


def _save_state(sb, kind, state):
    p = _state(sb, kind)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def _push_kernel(kind, code, datasets=()):
    slug = f"heritage-short-{kind}"
    with tempfile.TemporaryDirectory() as d:
        Path(d, "run.py").write_text(code, encoding="utf-8")
        Path(d, "kernel-metadata.json").write_text(json.dumps({
            "id": f"{user()}/{slug}", "title": slug, "code_file": "run.py", "language": "python", "kernel_type": "script",
            "is_private": True, "enable_gpu": True, "enable_internet": True, "dataset_sources": list(datasets),
            "competition_sources": [], "kernel_sources": [], "model_sources": []}))
        print("  " + kaggle("kernels", "push", "-p", d, "--accelerator", "NvidiaTeslaT4").strip().splitlines()[-1])
    return f"{user()}/{slug}"


def _push_dataset(folder, job_id):
    ref = f"{user()}/{DATASET}"
    (folder / "dataset-metadata.json").write_text(json.dumps({"title": DATASET, "id": ref, "licenses": [{"name": "other"}]}))
    if "ready" in kaggle("datasets", "status", ref, check=False):
        kaggle("datasets", "version", "-p", folder, "-m", job_id)
    else:
        kaggle("datasets", "create", "-p", folder)
    for _ in range(40):
        time.sleep(8)
        if "ready" in kaggle("datasets", "status", ref, check=False):
            files = kaggle("datasets", "files", ref, check=False)
            if f"{job_id}.txt" in files:
                return ref
    raise config.PipelineError("Kaggle dataset did not become ready")


def submit_wan(sb, ratios=("9x16", "16x9"), only=None):
    require_consent(sb)
    clips = []
    for ratio in ratios:
        for s in sb["shots"]:
            if (only and s["id"] not in only) or shots.has_wan(sb, s, ratio):
                continue
            inp = shots.wan_inputs(sb, s, ratio)
            clips.append({"item": f"{s['id']}_{ratio}", "shot": s["id"], "ratio": ratio, "key": cache.key(inp), "inputs": inp,
                          "motion_prompt": s["motion_prompt"], "seed": s["seed"], "size": inp["size"],
                          "keyframe_file": f"{s['id']}_{ratio}.jpg"})
    if not clips:
        print("  wan: nothing to submit, all clips are cached")
        return None
    job_id = "job-" + uuid.uuid4().hex[:10]
    v = sb["video"]
    job = {"job_id": job_id, "model": sb["models"]["video"], "clips": clips, "frames": v["frames"], "steps": v["steps"],
           "guidance": v["guidance"], "negative_prompt": v["negative_prompt"]}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for c in clips:
            shot = next(s for s in sb["shots"] if s["id"] == c["shot"])
            Image.open(keyframes.path(sb, shot, c["ratio"])).convert("RGB").save(d / c["keyframe_file"], quality=95)
        (d / "job.json").write_text(json.dumps(job), encoding="utf-8")
        (d / f"{job_id}.txt").write_text(job_id)
        ref = _push_dataset(d, job_id)
    code = (WORKERS / "wan_worker.py").read_text(encoding="utf-8").replace("@@JOB_ID@@", job_id)
    kernel = _push_kernel("wan", code, [ref])
    _save_state(sb, "wan", {"kernel": kernel, "submitted": time.time(), "job": job})
    print(f"  wan: submitted {len(clips)} clips as {kernel}")
    return kernel


def submit_music(sb):
    require_consent(sb)
    cands = []
    for seed in sb["music"]["seeds"]:
        inp = music.inputs(sb, seed)
        if not cache.fresh(music.path(sb, seed), inp):
            cands.append({**inp, "cache_key": cache.key(inp), "inputs": inp})
    if not cands:
        print("  music: nothing to submit, all candidates are cached")
        return None
    job = {"candidates": cands}
    code = (WORKERS / "music_worker.py").read_text(encoding="utf-8").replace("@@JOB@@", json.dumps(job))
    kernel = _push_kernel("music", code)
    _save_state(sb, "music", {"kernel": kernel, "submitted": time.time(), "job": job})
    print(f"  music: submitted {len(cands)} candidates as {kernel}")
    return kernel


def status(sb, kind):
    p = _state(sb, kind)
    if not p.exists():
        return "none"
    if not os.environ.get("KAGGLE_API_TOKEN") and not os.environ.get("KAGGLE_KEY"):
        return "no Kaggle login configured"
    text = kaggle("kernels", "status", json.loads(p.read_text(encoding="utf-8"))["kernel"], check=False)
    return parse_status(text)


def parse_status(text):
    """Only Kaggle's own status word counts; a network error message is 'unknown', not a failed job."""
    m = re.search(r'has status "(?:KernelWorkerStatus\.)?(\w+)"', text)
    word = m.group(1).lower() if m else "unknown"
    return "cancelled" if word.startswith("cancel") else word


def fetch(sb, kind):
    """Copy finished outputs whose inputs still match, and log each GPU call once."""
    state = json.loads(_state(sb, kind).read_text(encoding="utf-8"))
    items = {}
    if kind == "wan":
        for c in state["job"]["clips"]:
            items[c["item"]] = (c["key"], c["inputs"], out(sb, "shots", "wan", c["item"] + ".mp4"), c["seed"])
    else:
        for c in state["job"]["candidates"]:
            items[f"score_{c['seed']}"] = (c["cache_key"], c["inputs"], music.path(sb, c["seed"]), c["seed"])
    with tempfile.TemporaryDirectory() as d:
        print("  downloading", kind, "outputs")
        kaggle("kernels", "output", state["kernel"], "-p", d, check=False, timeout=1800)
        d = Path(d)
        for lg in d.glob("*.log"):
            shutil.copy(lg, _state(sb, kind).with_suffix(".kaggle.log"))
        res = d / "results.jsonl"
        if not res.exists():
            raise config.PipelineError(f"{kind} job produced no results; see {_state(sb, kind).with_suffix('.kaggle.log')}")
        rows = [json.loads(x) for x in res.read_text().splitlines() if x.strip()]
        logged = set(state.get("logged", []))
        for r in rows:
            name = r.get("item", r.get("event"))
            if name in logged:
                continue
            key, inp, target, seed = items.get(r.get("item"), (None, {}, None, None))
            error = r.get("error")
            if target is not None and r["key"] != key:
                error = "result belongs to another job"
            elif target is not None and r["status"] == "ok":
                target.parent.mkdir(parents=True, exist_ok=True)
                cache.store(target, (d / target.name).read_bytes(), inp)
            runlog.write({"run_id": runlog.RUN_ID, "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                          "stage": "shots" if kind == "wan" else "music", "item": name, "provider": "kaggle-2xT4",
                          "model": sb["models"]["video" if kind == "wan" else "music"], "params": inp, "seed": seed, "attempt": 1,
                          "status": "error" if error else r.get("status", "job_event"), "latency_s": r["seconds"],
                          "gpu_s": r["seconds"] if target is not None else 0.0,  # job events are running totals, not calls
                          "cost_usd": 0.0, "list_price_usd": None,
                          "output": {k: v for k, v in r.items() if k not in ("item", "key", "status", "error")}, "error": error})
            logged.add(name)
            print(f"  {name}: {'ERROR ' + error if error else 'ok'} {r['seconds']}s")
        state["logged"] = sorted(logged)
        _save_state(sb, kind, state)
