"""The services a film can use now, and how much of each is left.

Shown only if its key is set, it has already produced something on this computer, and its limit is known: from the service's own
answer (live) or from our call log (counted). Nothing here calls a model.
"""
import csv
import io
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

from . import gpu, keyframes, narration
from .core import budget, config, providers, settings

WRITERS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
GROQ = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]
NOT_TEXT = re.compile(r"image|banana|omni|tts|lyria|live|audio|transcribe|robotics|computer|embedding|decision|genie|antigravity|research|aqa|customtools|latest")

_kept: dict = {}


def _remember(name, seconds, get):
    """A service that does not answer is unknown, never zero."""
    hit = _kept.get(name)
    if hit and time.time() - hit[0] < (seconds if hit[1] is not None else 20):
        return hit[1]
    try:
        value = get()
    except Exception as e:  # noqa: BLE001 - a limit display must never break the studio
        print(f"limits: {name} did not answer ({type(e).__name__})")
        value = None
    _kept[name] = (time.time(), value)
    return value


def has(*names):
    return all(os.environ.get(n, "").strip() for n in names)


def _kaggle():
    rows = list(csv.DictReader(io.StringIO(gpu.kaggle("quota", "-v", timeout=40))))
    g = next(r for r in rows if r["resource"] == "GPU")
    number = lambda x: float(re.sub(r"[^\d.]", "", x))  # noqa: E731
    return {"used": number(g["used"]), "total": number(g["total"]), "reset": g["refreshAt"]}


def live(fresh=False):
    if fresh:
        _kept.clear()
    jobs = {"gemini": (600, providers.gemini_models, has("GEMINI_API_KEY")), "addis": (60, providers.addis_usage, has("ADDIS_API_KEY")),
            "kaggle": (120, _kaggle, has("KAGGLE_API_TOKEN") or has("KAGGLE_USERNAME", "KAGGLE_KEY"))}
    with ThreadPoolExecutor(3) as pool:
        waiting = {k: pool.submit(_remember, k, s, f) for k, (s, f, ok) in jobs.items() if ok}
        return {k: waiting[k].result() if k in waiting else None for k in jobs}


def meter(used, limit, unit, reset=None, source="counted", full=False):
    """full: the service says the limit is reached, whatever we counted."""
    return {"used": used, "limit": limit, "unit": unit, "reset": reset, "source": source, "full": full}


def google_meter(model):
    use, limit = budget.google_used().get(model, 0), budget.day_limit(model)
    return meter(use, limit, "calls", budget.tts_reset().isoformat(), "counted", budget.google_blocked(model))


def google_state(model):
    """Can this model be used now? Judged only from what Google has answered us."""
    limit = budget.day_limit(model)
    if limit == 0:
        return "off", "Not on the free tier"
    if budget.google_blocked(model) or (limit is not None and budget.google_used().get(model, 0) >= limit):
        return "wait", "Used up"
    return "ok", ""


def option(oid, name, *, on=False, wait=False, m=None, note=""):
    """wait: it works, but nothing is left until m's reset."""
    return {"id": oid, "name": name, "on": on, "wait": wait, "meter": m, "note": note}


def _google_voices(seen):
    """Voice models that have already made a voice here, are still offered, and are on the free tier."""
    names = [m for m in budget.worked("gemini") if "-tts" in m and (not seen or m in seen) and google_state(m)[0] != "off"]
    return sorted(names, key=lambda m: [-float(x) for x in re.findall(r"\d+\.\d+", m)] + ["lite" in m])


def _short(name):
    return name.replace(" Preview", "").replace(" TTS", "")


def _voice(sb, seen, now):
    lang = sb["language"]
    v, eng = sb["voices"][lang], narration.engine(sb, lang)
    current = v.get("model", sb["models"]["tts"])
    rows, w = [], now["addis"]
    if w and budget.worked("addis-ai"):
        cost = narration.estimate_s(sb, lang) / 60 * w["per_minute"]
        rows.append(option("addis", "Addis AI", on=eng == "addis", wait=w["balance"] <= 0, m=meter(round(w["start"] - w["balance"], 2), w["start"], w["currency"], None, "live"),
                           note=f"No emotion setting. About {cost:.0f} {w['currency']} for this film"))
    if has("GEMINI_API_KEY"):
        rows += [option(f"gemini:{m}", _short(seen.get(m, {}).get("name") or m), on=eng == "gemini" and current == m, wait=google_state(m)[0] == "wait", m=google_meter(m), note="Emotion for each line") for m in _google_voices(seen)]
    if _gpu(now) and (eng == "omnivoice" or budget.worked("kaggle", "narration")):
        rows.append(option("omnivoice", "OmniVoice", on=eng == "omnivoice", m=_gpu(now), note="Neutral voice, on the GPU"))
    return rows


def _gpu(now):
    k = now["kaggle"]
    return k and meter(round(k["used"], 1), round(k["total"]), "GPU hours", k["reset"], "live")


def _pictures(sb, now):
    use, rows = keyframes.service(sb), []
    each = keyframes.cost(sb, sb["shots"][0], "9x16")
    left = budget.flux_left()
    if has("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN") and budget.worked("cloudflare"):
        rows.append(option("cloudflare", "Cloudflare FLUX.2", on=use == "cloudflare", wait=left < each, note="Each picture is checked",
                           m=meter(budget.FLUX_PER_DAY // each - left // each, budget.FLUX_PER_DAY // each, "pictures", budget.flux_reset().isoformat())))
    if _gpu(now) and (use == "kaggle" or budget.worked("kaggle", "keyframes")):
        rows.append(option("kaggle", "Kaggle FLUX.2", on=use == "kaggle", m=_gpu(now), note="In one batch, not checked"))
    return rows


def _motion(sb, now):
    clips = [s.get("motion", "clip") for s in sb["shots"]]
    count = lambda x: f"{clips.count(x)} shot{'s' * (clips.count(x) != 1)}"  # noqa: E731
    who = sb.get("services", {}).get("animate", "kaggle")
    rows = [option("clip", "Real movement · Kaggle", on="clip" in clips and who == "kaggle", m=_gpu(now), note=f"{count('clip')}. Free GPU, about {round(budget.clip_seconds() / 60)} minutes a clip")] if _gpu(now) and budget.worked("kaggle", "shots") else []
    if os.environ.get("WAVESPEED_API_KEY", "").strip():
        spent = sum(r.get("cost_usd") or 0 for r in budget.rows() if r.get("provider") == "wavespeed")
        tried = "" if budget.worked("wavespeed") else " Not tried here yet."
        from . import wavespeed
        cap, real = float(settings.load()["wavespeed_budget"]), wavespeed.balance()
        rows.append({**option("wavespeed", "Real movement · WaveSpeed", on=any(s.get("motion", "clip") == "clip" and s.get("animate") == "wavespeed" for s in sb["shots"]),
                              m=meter(budget.wavespeed_spent(), cap, "dollars"),
                              note=f"Paid: Fast $0.05 or $0.08 a clip, Standard $0.15 or $0.24, 1 to 3 minutes. Chosen shot by shot on the Shots tab; Kaggle makes the rest. Account balance: {'$%.2f' % real if real is not None else 'not answered'}.{tried}"), "paid": True})
    return rows + [option("camera", "Camera move", on=all(m == "camera" for m in clips), note=f"{count('camera')}. Free")]


def _music(now):
    return [option("ace", "ACE-Step", on=True, m=_gpu(now), note="Three scores, about 6 minutes")] if _gpu(now) and budget.worked("kaggle", "music") else []


def _writing():
    """A choice only when there is one: models with a limit we know, beside the one in use."""
    use = settings.load()["writer"]
    limits = budget.groq_limits()
    rows = [option("auto", "Google", on=use == "auto", note="The first model that answers")]
    rows += [option(f"gemini:{m}", m, on=use == f"gemini:{m}", wait=google_state(m)[0] == "wait", m=google_meter(m)) for m in budget.worked("gemini")
             if kind_of(m) == "Writing" and (use == f"gemini:{m}" or budget.day_limit(m))]
    for m in GROQ if has("GROQ_API_KEY") else []:
        x = limits.get(m)
        if x or use == f"groq:{m}" or m in (_remember("groq", 600, providers.groq_models) or []):
            rows.append(option(f"groq:{m}", "Groq " + m.split("/")[1], on=use == f"groq:{m}", wait=bool(x) and not x["left"], note="Checks pictures too" if "qwen" in m else "Writes only",
                               m=meter(x["limit"] - x["left"], x["limit"], "calls", None, "live") if x else None))
    return rows if len(rows) > 1 else []


def kind_of(m):
    for kind, pattern in (("Voice", r"tts"), ("Pictures", r"image|banana"), ("Video", r"omni|genie"), ("Music", r"lyria"), ("Writing", None)):
        if pattern and re.search(pattern, m):
            return kind
    return "Other" if NOT_TEXT.search(m) or not m.startswith("gemini-") else "Writing"


def state(sb, fresh=False):
    now = live(fresh)
    groups = [("voice", "Voice", _voice(sb, now["gemini"] or {}, now)), ("pictures", "Pictures", _pictures(sb, now)), ("motion", "Motion", _motion(sb, now)), ("music", "Music", _music(now)), ("writing", "Script", _writing())]
    return {"groups": [{"id": i, "title": x, "options": o} for i, x, o in groups if o]}


def check_writer(choice):
    if choice != "auto" and not re.fullmatch(r"gemini:gemini-[a-z0-9.\-]{1,60}", choice) and choice not in {f"groq:{m}" for m in GROQ}:
        raise config.PipelineError("Unknown writing model.")
    if choice.startswith("gemini:") and kind_of(choice[7:]) != "Writing":
        raise config.PipelineError("That model does not write text.")
