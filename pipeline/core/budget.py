"""What is left of each free limit, counted from runs.jsonl. Estimates: use elsewhere on the same accounts is not seen."""
import json
import re
import statistics
from datetime import datetime, timedelta, timezone

from . import config, runlog


def mine(r):
    """Made with the account in .env now. Rows from before accounts were noted (26 Nov, 08:40 EAT) belong to the first accounts,
    which are no longer in .env, so a new key starts with its full free limit."""
    return r.get("account") == runlog.account(r.get("provider"))

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
        if "tts" in (r.get("model") or "") and _since(r, t) and mine(r):
            m = used.setdefault(r["model"], {"used": 0, "blocked": False})
            m["used"] += r["status"] == "ok"
            m["blocked"] |= r["status"] == "error" and re.search(r"per day|limit: 0\b", r.get("error") or "", re.I) is not None
    return used


def google_used():
    """Calls each Google model answered since Google's last daily reset."""
    used, t = {}, windows()["tts"]
    for r in rows():
        if r.get("provider") == "gemini" and r["status"] == "ok" and _since(r, t) and mine(r):
            used[r["model"]] = used.get(r["model"], 0) + 1
    return used


def worked(provider, stage=None):
    """Models of a provider that have really produced something, in the order they first did."""
    return list(dict.fromkeys(r["model"] for r in rows() if str(r.get("provider", "")).startswith(provider) and r["status"] == "ok" and r.get("model") and (not stage or r.get("stage") == stage)))


def google_blocked(model):
    t = windows()["tts"]
    return any(r.get("model") == model and r["status"] == "error" and _since(r, t) and mine(r) and re.search(r"per day", r.get("error") or "", re.I) for r in rows())


def day_limit(model):
    """Google publishes no limit we can ask for, so this is what its refusals have told us. None: not known yet. 0: not on the free tier."""
    found = None
    for r in rows():
        if r.get("model") != model or r["status"] != "error":
            continue
        e = r.get("error") or ""
        if "429" in e and re.search(r"limit: 0\b", e):
            found = 0
        elif m := re.search(r"limit: (\d+)(?: requests|[^*]{0,160}?requests) per day", e):
            found = int(m[1])
    return TTS_PER_DAY if found is None and "tts" in model else found


def groq_limits():
    """What Groq said about today's limit in its latest answer, by model."""
    found = {}
    for r in rows():
        x = (r.get("output") or {}).get("limits") if r.get("provider") == "groq" and isinstance(r.get("output"), dict) else None
        if x and datetime.now(timezone.utc) - datetime.fromisoformat(r["ts"]) < timedelta(days=1):
            found[r["model"]] = x
    return found


def _flux_rows():
    return [r for r in rows() if "flux" in (r.get("model") or "") and r.get("provider") == "cloudflare" and mine(r)]


def _neurons(r):
    return (r.get("list_price_usd") or 0) / 0.011 * 1000


def _flux_blocked():
    """When Cloudflare last said the free allocation was used up, if nothing was drawn since."""
    last = None
    for r in _flux_rows():
        if r["status"] == "ok":
            last = None
        elif re.search("free allocation|free pictures are used up", r.get("error") or ""):
            last = datetime.fromisoformat(r["ts"])
    return last


def wavespeed_spent():
    """Dollars spent with the WaveSpeed key in .env, redos included."""
    return round(sum(r.get("cost_usd") or 0 for r in rows() if r.get("provider") == "wavespeed" and r["status"] == "ok" and mine(r)), 2)


def wavespeed_left():
    from . import settings
    return round(max(0.0, float(settings.load()["wavespeed_budget"]) - wavespeed_spent()), 2)


def flux_drawn():
    t = windows()["flux"]
    return sum(1 for r in _flux_rows() if r["status"] == "ok" and _since(r, t))


def tts_left(model):
    m = tts_used().get(model, {"used": 0, "blocked": False})
    return 0 if m["blocked"] else max(0, TTS_PER_DAY - m["used"])


def tts_reset():
    return windows()["tts"] + timedelta(days=1)


def flux_used():
    """Cloudflare counts the last 24 hours, not since midnight: on 26 Nov it refused at 08:22 EAT,
    when our log showed 10,095 units drawn in the 24 hours before and only 220 since midnight UTC."""
    return FLUX_PER_DAY - flux_left()


def flux_left(now=None):
    now = now or datetime.now(timezone.utc)
    left = FLUX_PER_DAY - sum(_neurons(r) for r in _flux_rows() if _since(r, now - timedelta(days=1)))
    b = _flux_blocked()
    if b:  # Cloudflare's count beats ours: only what has dropped out of its window since it refused is free
        left = min(left, sum(_neurons(r) for r in _flux_rows() if b - timedelta(days=1) <= datetime.fromisoformat(r["ts"]) < now - timedelta(days=1)))
    return max(0, round(left))


def flux_reset(need=2000):
    """When there is room again for about a dozen pictures: each one drops out 24 hours after it was drawn.
    With room now, when the oldest counted picture drops out. Always in the future: the page reloads when it passes."""
    now = datetime.now(timezone.utc)
    if flux_left(now) >= need:
        counted = [datetime.fromisoformat(r["ts"]) + timedelta(days=1) for r in _flux_rows()]
        return min([t for t in counted if t > now], default=now + timedelta(days=1))
    for r in _flux_rows():
        at = datetime.fromisoformat(r["ts"]) + timedelta(days=1, seconds=1)
        if at > now and flux_left(at) >= need:
            return at
    return now + timedelta(days=1)


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
