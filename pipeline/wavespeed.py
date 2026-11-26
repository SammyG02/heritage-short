"""Moving clips on WaveSpeed (paid): Wan 2.2, hosted, a minute or two a clip.

Docs read 26 Nov 2026: https://wavespeed.ai/docs/docs-api/wavespeed-ai/wan-2.2/i2v-480p, .../i2v-480p-ultra-fast and /docs/upload-files-api.
Submit once and poll; a submit is never retried by itself, because a second submit is a second paid clip.
Spending is capped in dollars (settings: wavespeed_budget), counted from the call log for the key in .env.
Uploads and outputs are kept by WaveSpeed for up to 7 days (their retention page); the clip is downloaded at once.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from . import keyframes, shots
from .core import approvals, budget, cache, config, runlog
from .core.storyboard import require_consent, require_service

API = "https://api.wavespeed.ai/api/v3"
POLL_S, WAIT_S = 3, 20 * 60
AT_ONCE = 2  # the account's plan allows 2 running clips (HTTP 429 "Concurrency limit reached", 26 Nov 2026)
DONE, FAILED = "completed", ("failed", "cancelled", "timeout", "deleted")


def _headers():
    return {"Authorization": "Bearer " + config.secret("WAVESPEED_API_KEY")}


_balance = [0.0, None]  # (when asked, USD)


def balance(fresh=False):
    """The account's real USD balance, from WaveSpeed itself; None if it does not answer. Asked at most once a minute.
    Docs (26 Nov 2026) give two paths: /balance in the API reference and /account/balance in a how-to; the first that answers wins."""
    if not fresh and time.time() - _balance[0] < 60:
        return _balance[1]
    found = None
    for path in ("balance", "account/balance"):
        try:
            r = requests.get(f"{API}/{path}", headers=_headers(), timeout=15)
            if r.ok:
                found = float((r.json().get("data") or {})["balance"])
                break
        except (requests.RequestException, KeyError, TypeError, ValueError, config.PipelineError):
            continue
    _balance[:] = [time.time(), found]
    return found


def left(fresh=False):
    """What may be spent now: your budget, never more than what is really in the account."""
    real = balance(fresh)
    return round(min(budget.wavespeed_left(), real), 2) if real is not None else budget.wavespeed_left()


def upload(path):
    """Two steps: ask for an upload slot, then PUT the bytes to it. Returns the URL WaveSpeed can read."""
    data = path.read_bytes()
    r = requests.post(f"{API}/media/uploads", headers={**_headers(), "Content-Type": "application/json"},
                      json={"filename": path.name, "size": len(data), "content_type": "image/png"}, timeout=60)
    if not r.ok:
        raise config.PipelineError(f"WaveSpeed refused the upload: HTTP {r.status_code} {r.text[:200]}")
    slot = r.json()["data"]
    put = requests.put(slot["upload"]["url"], headers=slot["upload"].get("headers") or {}, data=data, timeout=120)  # no key: a signed URL
    if not 200 <= put.status_code < 300:
        raise config.PipelineError(f"The picture did not reach WaveSpeed: HTTP {put.status_code}")
    return slot["download_url"]


def clip(item, image_url, inp):
    """One paid call. Returns the MP4 bytes."""
    cost = shots.wave_cost(inp["model"], inp["seconds"])
    params = {"prompt": inp["motion_prompt"], "image": "(uploaded keyframe)", "duration": inp["seconds"], "seed": inp["seed"], "negative_prompt": inp["negative_prompt"]}
    with runlog.call("shots", item, "wavespeed", inp["model"], params, inp["seed"], 1) as rec:
        for _ in range(20):  # "Concurrency limit reached": nothing was created or charged, so wait and send it again
            r = requests.post(f"{API}/{inp['model']}", headers={**_headers(), "Content-Type": "application/json"}, timeout=60,
                              json={"prompt": inp["motion_prompt"], "image": image_url, "negative_prompt": inp["negative_prompt"], "duration": inp["seconds"], "seed": inp["seed"]})
            if r.status_code != 429 or "oncurrency" not in r.text:
                break
            time.sleep(15)
        if not r.ok:
            raise config.PipelineError(f"WaveSpeed refused the clip: HTTP {r.status_code} {r.text[:300]}")
        body = r.json()
        pid = (body.get("data") or body)["id"]
        rec["output"] = {"prediction": pid}
        end = time.time() + WAIT_S
        while time.time() < end:
            time.sleep(POLL_S)
            try:
                g = requests.get(f"{API}/predictions/{pid}/result", headers=_headers(), timeout=30)
            except requests.RequestException:
                continue  # keep polling: the clip is already paid for
            if g.status_code == 429 or g.status_code >= 500:
                time.sleep(10)
                continue
            d = g.json().get("data") or {}
            if d.get("status") == DONE:
                video = requests.get(d["outputs"][0], timeout=300)
                video.raise_for_status()
                rec["cost_usd"] = rec["list_price_usd"] = cost
                rec["output"].update({"bytes": len(video.content), "inference_ms": (d.get("timings") or {}).get("inference")})
                return video.content
            if d.get("status") in FAILED:
                raise config.PipelineError(f"WaveSpeed could not make it: {d.get('error') or d.get('status')}")
        raise config.PipelineError(f"WaveSpeed took over {WAIT_S // 60} minutes. It may still finish: prediction {pid}.")


def todo(sb, ratios=None, only=None):
    """WaveSpeed shots whose picture is approved and whose clip is missing or asked for again."""
    found = []
    for r in ratios or keyframes.drawn(sb):
        for s in sb["shots"]:
            if (only and s["id"] not in only) or s.get("motion", "clip") == "camera" or shots.animator(sb, s) != "wavespeed" or shots.has_wan(sb, s, r):
                continue
            p = keyframes.path(sb, s, r)
            if p.exists() and cache.fresh(p, keyframes.inputs(sb, s, r)) and approvals.ok(sb, "picture", p.stem, cache.file_sha(p)):
                found.append((s, r))
    return found


def run(sb, ratios=None, only=None):
    require_consent(sb)
    require_service(sb, "wavespeed")
    real = balance(fresh=True)
    jobs, left = todo(sb, ratios, only), (min(budget.wavespeed_left(), real) if real is not None else budget.wavespeed_left())
    print(f"  WaveSpeed balance: {'$%.2f' % real if real is not None else 'not answered'}; budget left ${budget.wavespeed_left():.2f}")
    plan, total = [], 0.0
    for s, r in jobs:  # in shot order, while the money lasts
        c = shots.wave_price(sb, s)
        if total + c <= left + 1e-9:
            plan.append((s, r))
            total += c
    if jobs and not plan:
        raise config.PipelineError(f"Only ${left:.2f} can be spent on WaveSpeed (your budget or the account's real balance, whichever is lower), not enough for one more clip. Use Kaggle for the rest.")
    if len(plan) < len(jobs):
        print(f"  {len(jobs) - len(plan)} clips not sent: they would pass your WaveSpeed budget (${left:.2f} left)")
    print(f"  motion: {len(plan)} clips on WaveSpeed {shots.wave_model(sb)}, about ${total:.2f}")
    failed, done, lock = [], [0], threading.Lock()

    def one(job):
        s, r = job
        inp, p = shots.wan_inputs(sb, s, r, "wavespeed"), shots.wan_path(sb, s, r)
        try:
            image = upload(keyframes.path(sb, s, r))
            data = clip(f"{s['id']}_{r}", image, inp)
        except (config.PipelineError, requests.RequestException, KeyError, ValueError) as e:
            with lock:
                print(f"  {s['id']}_{r}: {e}", flush=True)
                failed.append(s["id"])
            return
        with lock:
            shots.keep_clip(p)
            cache.store(p, data, inp)
            cache.stamp(p, inp, seconds=shots.seconds_of(p))
            done[0] += 1
            print(f"  clip {s['id']}_{r} ready", flush=True)
            runlog.progress(done[0] + 1 if done[0] < len(plan) else done[0], len(plan), f"{done[0]} of {len(plan)} clips back")

    # Several at once: WaveSpeed works on them in parallel, so the batch takes about as long as its slowest clip.
    runlog.progress(1, len(plan), "sending the pictures")
    runlog.step(f"WaveSpeed is animating {min(AT_ONCE, len(plan))} shots at a time, usually 1 to 3 minutes each")
    before = balance(fresh=True) if len(plan) == 1 else None
    with ThreadPoolExecutor(AT_ONCE) as pool:
        list(pool.map(one, plan))
    after = balance(fresh=True) if before is not None and not failed else None
    if after is not None:
        print(f"  WaveSpeed charged ${before - after:.2f} for this clip (balance ${before:.2f} -> ${after:.2f})", flush=True)
    if failed:
        raise config.PipelineError(f"{len(plan) - len(failed)} clips made; these failed: {', '.join(failed)}. Press Animate again to retry them.")
