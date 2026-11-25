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

from . import keyframes, music, narration, shots
from .core import budget, cache, config, runlog
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


def _push_dataset(folder, job_id, name=DATASET):
    ref = f"{user()}/{name}"
    (folder / "dataset-metadata.json").write_text(json.dumps({"title": name, "id": ref, "licenses": [{"name": "other"}]}))
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


def submit_wan(sb, ratios=("9x16", "16x9"), only=None, hours=None):
    require_consent(sb)
    clips = []
    chosen, left_out, wait, need_h = shots.plan(sb, ratios, only, hours)
    print(f"  motion: {len(chosen)} clips, about {need_h:.1f} of {budget.gpu_left_h():.1f} GPU hours left; "
          f"{len(left_out)} left out by the limit, {len(wait)} waiting for an approved picture")
    for s, ratio in chosen:
        inp = shots.wan_inputs(sb, s, ratio)
        clips.append({"item": f"{s['id']}_{ratio}", "shot": s["id"], "ratio": ratio, "key": cache.key(inp), "inputs": inp,
                      "motion_prompt": inp["motion_prompt"], "seed": s["seed"], "size": inp["size"],
                      "keyframe_file": f"{s['id']}_{ratio}.jpg"})
    if not clips:
        print("  wan: nothing to submit")
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


def submit_pictures(sb, ratios=("9x16", "16x9"), only=None):
    """Backup for the picture limit: the same model on the free GPU. Pictures come back marked as unchecked."""
    require_consent(sb)
    rows, files, wait = [], {}, []
    for ratio in ratios:
        for s in sb["shots"]:
            p, inp = keyframes.path(sb, s, ratio), keyframes.inputs(sb, s, ratio)
            if (only and s["id"] not in only) or cache.fresh(p, inp):
                continue
            if not keyframes.voice_ok(sb, s) or not keyframes.cast_ready(sb, s):
                wait.append(p.stem)
                continue
            names = [keyframes.ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in s["references"]]
            files.update({f.stem + ".jpg": f for f in names})
            rows.append({"item": p.stem, "key": cache.key(inp), "inputs": inp, "prompt": inp["prompt"], "size": inp["size"], "seed": inp["seed"], "files": [f.stem + ".jpg" for f in names]})
    if wait:
        print("  waiting for an approved voice or a chosen cast: " + ", ".join(wait))
    if not rows:
        print("  pictures: nothing to submit")
        return None
    job_id = "job-" + uuid.uuid4().hex[:10]
    job = {"job_id": job_id, "pictures": rows}
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for name, f in files.items():
            im = Image.open(f).convert("RGB")
            im.thumbnail((768, 768))
            im.save(d / name, quality=95)
        (d / "job.json").write_text(json.dumps(job), encoding="utf-8")
        (d / f"{job_id}.txt").write_text(job_id)
        ref = _push_dataset(d, job_id, "heritage-short-pictures")
    kernel = _push_kernel("pictures", (WORKERS / "pictures_worker.py").read_text(encoding="utf-8").replace("@@JOB_ID@@", job_id), [ref])
    _save_state(sb, "pictures", {"kernel": kernel, "submitted": time.time(), "job": job})
    print(f"  pictures: submitted {len(rows)} as {kernel}")
    return kernel


def submit_voice(sb, lang):
    """Last resort: OmniVoice. Only when the storyboard chooses that engine."""
    if narration.engine(sb, lang) != "omnivoice":
        raise config.PipelineError("This film does not use OmniVoice. Choose it as the voice service first.")
    todo = narration.stale(sb, lang)
    if not todo:
        print("  voice: nothing to submit")
        return None
    narration.check_ready(sb, lang, todo)
    lines = []
    for s in todo:
        for i, turn in enumerate(narration.parts(sb, s, lang), 1):
            lines.append({"item": f"{s['id']}_{i}", "shot": s["id"], "n": i, "key": cache.key(turn), "inputs": turn, "text": turn["text"], "voice": turn["voice"]})
    job = {"model": narration.ENGINES["omnivoice"], "lang": lang, "lines": lines}
    kernel = _push_kernel("voice", (WORKERS / "voice_worker.py").read_text(encoding="utf-8").replace("@@JOB@@", json.dumps(job, ensure_ascii=False)))
    _save_state(sb, "voice", {"kernel": kernel, "submitted": time.time(), "job": job})
    print(f"  voice: submitted {len(lines)} lines as {kernel}")
    return kernel


def _join_voices(sb, job):
    if narration.engine(sb, job["lang"]) != "omnivoice":
        return  # the film has moved to another service since; the parts are kept
    for s in sb["shots"]:
        turns = narration.parts(sb, s, job["lang"])
        files = [narration.part_path(sb, s, job["lang"], i) for i in range(1, len(turns) + 1)]
        if all(cache.fresh(f, t) for f, t in zip(files, turns)):
            cache.store(narration.path(sb, s, job["lang"]), narration.join(files), narration.inputs(sb, s, job["lang"]), model_used=job["model"])


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
    elif kind == "pictures":
        for c in state["job"]["pictures"]:
            items[c["item"]] = (c["key"], c["inputs"], out(sb, "keyframes", c["item"] + ".png"), c["seed"])
    elif kind == "voice":
        for c in state["job"]["lines"]:
            items[c["item"]] = (c["key"], c["inputs"], out(sb, "narration", state["job"]["lang"], "omnivoice", "parts", c["item"] + ".wav"), 7)
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
                if kind == "pictures":
                    keyframes.keep_version(target)
                    cache.store(target, (d / target.name).read_bytes(), inp, qa={"status": "unchecked, drawn on the GPU", "seed_used": seed, "tries": []})
                else:
                    cache.store(target, (d / target.name).read_bytes(), inp)
            runlog.write({"run_id": runlog.RUN_ID, "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                          "stage": {"wan": "shots", "voice": "narration", "pictures": "keyframes"}.get(kind, "music"), "item": name, "provider": "kaggle-2xT4",
                          "model": "black-forest-labs/FLUX.2-klein-4B" if kind == "pictures" else state["job"]["model"] if kind == "voice" else sb["models"]["video" if kind == "wan" else "music"], "params": inp, "seed": seed, "attempt": 1,
                          "status": "error" if error else r.get("status", "job_event"), "latency_s": r["seconds"],
                          "gpu_s": r["seconds"] if target is not None else 0.0,  # job events are running totals, not calls
                          "cost_usd": 0.0, "list_price_usd": None,
                          "output": {k: v for k, v in r.items() if k not in ("item", "key", "status", "error")}, "error": error})
            logged.add(name)
            print(f"  {name}: {'ERROR ' + error if error else 'ok'} {r['seconds']}s")
        state["logged"] = sorted(logged)
        _save_state(sb, kind, state)
        if kind == "voice":
            _join_voices(sb, state["job"])
