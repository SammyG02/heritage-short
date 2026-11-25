"""What is left of each free limit, counted from runs.jsonl. Estimates: use elsewhere on the same accounts is not seen."""
import json
import re
import statistics
from datetime import datetime, timedelta, timezone

from . import config

TTS_PER_DAY = 10
FLUX_PER_DAY = 10000
FLUX_PER_PICTURE = 167
GPU_H_PER_WEEK = 30
GPU_RESERVE_H = 2     # kept back for retakes
GPU_SESSION_H = 8     # one Kaggle session is limited, so never plan a longer job
CLIP_S_DEFAULT = 1200


def rows():
    found = []
    for log in (config.RUNS, config.FILMS / "runs.jsonl"):  # the free limits are shared by every film on this computer
        for line in log.read_text(encoding="utf-8").splitlines() if log.exists() else []:
            try:
                found.append(json.loads(line))
            except ValueError:
                continue
    return found


def windows():
    """Start of the current free window for each service, in UTC."""
    now = datetime.now(timezone.utc)
    pacific = now - timedelta(hours=8)  # Google resets at midnight Pacific; standard time in November
    tts = pacific.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=8)
    flux = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"tts": tts, "flux": flux, "gpu": flux - timedelta(days=(now.weekday() - 5) % 7)}  # Kaggle: Saturday 00:00 UTC


def local(t):
    return t.astimezone().strftime("%a %H:%M")


def _since(r, t):
    return datetime.fromisoformat(r["ts"]) >= t


def tts_used():
    used, t = {}, windows()["tts"]
    for r in rows():
        if "tts" in (r.get("model") or "") and _since(r, t):
            m = used.setdefault(r["model"], {"used": 0, "blocked": False})
            m["used"] += r["status"] == "ok"
            m["blocked"] |= r["status"] == "error" and re.search(r"per day|limit: 0\b", r.get("error") or "", re.I) is not None
    return used


def tts_left(model):
    m = tts_used().get(model, {"used": 0, "blocked": False})
    return 0 if m["blocked"] else max(0, TTS_PER_DAY - m["used"])


def tts_reset():
    return windows()["tts"] + timedelta(days=1)


def flux_used():
    t = windows()["flux"]
    return round(sum((r.get("list_price_usd") or 0) for r in rows() if "flux" in (r.get("model") or "") and _since(r, t)) / 0.011 * 1000)


def flux_left():
    return max(0, FLUX_PER_DAY - flux_used())


def flux_reset():
    return windows()["flux"] + timedelta(days=1)


def gpu_used_h():
    """Each job's own total (its 'done' row) when logged, so loading time counts and clips are not counted twice."""
    t, jobs = windows()["gpu"], {}
    for r in rows():
        if str(r.get("provider", "")).startswith("kaggle-") and _since(r, t):
            j = jobs.setdefault((r["run_id"], r["stage"]), [0, 0])
            if r["item"] == "done":
                j[0] = max(j[0], r["latency_s"] or 0)
            elif r["item"] != "loaded":
                j[1] += r.get("gpu_s") or 0
    return sum(max(j) for j in jobs.values()) / 3600


def gpu_left_h():
    return max(0.0, GPU_H_PER_WEEK - gpu_used_h())


def clip_seconds():
    done = [r["latency_s"] for r in rows() if r.get("stage") == "shots" and r["status"] == "ok" and "denoise_s" in (r.get("output") or {})]
    return statistics.median(done) if done else CLIP_S_DEFAULT
