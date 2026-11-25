"""The studio: a local web app over the same stages as the command line.

It listens on this computer only. Every button that uses a model is one explicit request, and only one job runs at a time.
"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import keyframes, music, narration, script, shots
from .core import approvals, budget, cache, config, providers, runlog
from .core.storyboard import out, root, validate

PORT = 8765
STATIC = Path(__file__).parent / "web_static"
MEDIA = {".png", ".jpg", ".wav", ".mp4", ".srt"}
EDIT_SHOT = {"image_prompt", "motion_prompt", "emotion", "voice_emotion", "seed", "motion"}
GEMINI_VOICES = [("Algieba", "man"), ("Charon", "man"), ("Iapetus", "man"), ("Orus", "man"), ("Puck", "man"),
                 ("Sulafat", "woman"), ("Achernar", "woman"), ("Kore", "woman"), ("Aoede", "woman"), ("Leda", "woman")]
lock = threading.RLock()
job: dict = {}
planned: dict = {}  # by action


class Refused(config.PipelineError):
    pass


# ---------------------------------------------------------------- storyboards

def index():
    found = {}
    places = sorted(config.FILMS.glob("*/storyboard.json"), key=lambda p: -p.stat().st_mtime)
    if os.environ.get("SHOW_REPO_FILM", "").strip() == "1":  # the repository's film is its author's story, not part of the tool
        places = [config.ROOT / "storyboard.json", *places, *sorted((config.ROOT / "storyboards").glob("*.json"))]
    for p in places:
        try:
            found.setdefault(json.loads(p.read_text(encoding="utf-8"))["id"], p)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return found


def open_board(fid):
    p = index().get(fid)
    if not p:
        raise Refused("That film does not exist.")
    return p, json.loads(p.read_text(encoding="utf-8"))


def save_board(p, sb):
    errors = validate(sb)
    if errors:
        raise Refused("Not saved: " + "; ".join(errors[:4]))
    part = p.with_suffix(".part")
    part.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    part.replace(p)


def url(path):
    """A link that changes when the file changes, so the browser never shows an old version."""
    if not path.exists():
        return None
    base = config.FILMS if config.FILMS in path.parents else config.OUTPUTS
    return f"/files/{path.relative_to(base).as_posix()}?v={int(path.stat().st_mtime)}"


def asset(path, inputs):
    return {"url": url(path), "fresh": cache.fresh(path, inputs)}


def film_state(fid):
    p, sb = open_board(fid)
    lang = sb["language"]
    rows = []
    for s in sb["shots"]:
        wav = narration.path(sb, s, lang)
        row = {"id": s["id"], "cast_ok": keyframes.cast_ready(sb, s), "script_ok": approvals.ok(sb, "script", s["id"], approvals.script_key(s)), "voice_ok": approvals.ok(sb, "voice", s["id"], narration.approval_key(sb, s, lang)),
               "voice": asset(wav, narration.inputs(sb, s, lang))}
        if wav.exists():
            row["voice"]["seconds"] = round(narration.seconds(wav), 1)
            row["voice"]["model"] = cache.read_meta(wav).get("model_used")
        for r in keyframes.SIZES:
            kf = keyframes.path(sb, s, r)
            a = {**asset(kf, keyframes.inputs(sb, s, r)), "cost": round(keyframes.cost(sb, s, r))}
            row[f"picture_{r}"] = {**a, "qa": cache.read_meta(kf).get("qa"), "ok": a["fresh"] and approvals.ok(sb, "picture", kf.stem, cache.file_sha(kf)),
                                   "versions": [{"name": v.name, "url": url(v)} for v in keyframes.versions(kf)[-4:]]}
            row[f"clip_{r}"] = asset(shots.wan_path(sb, s, r), shots.wan_inputs(sb, s, r))
        rows.append(row)
    refs = {}
    for name, ref in sb["references"].items():
        opts = []
        for seed in ref["seeds"]:
            f = keyframes.ref_path(sb, name, seed)
            opts.append({"seed": seed, **asset(f, keyframes.ref_inputs(sb, name, seed))})
        refs[name] = {"options": opts, "chosen": ref["chosen_seed"], "decided": ref["reason"] != "Not chosen yet" and any(o["seed"] == ref["chosen_seed"] and o["fresh"] for o in opts), "from": ref.get("from"), "reason": ref["reason"],
                      "look": ref.get("look", ""), "shots": [s["id"] for s in sb["shots"] if name in s["references"]]}
    scores = [{"seed": x, **asset(music.path(sb, x), music.inputs(sb, x))} for x in sb["music"]["seeds"]]
    folder = out(sb, "film", lang)
    report = folder / "report.json"
    gpu_jobs = {}
    for kind in ("wan", "music", "voice", "pictures"):
        f = out(sb, "jobs", f"{kind}.json")
        if f.exists():
            j = json.loads(f.read_text(encoding="utf-8"))
            items = j["job"].get("clips") or j["job"].get("candidates") or j["job"].get("lines") or j["job"].get("pictures") or []
            gpu_jobs[kind] = {"submitted": j["submitted"], "items": len(items), "fetched": "done" in j.get("logged", [])}
    fb = feedback_path(fid)
    chosen, left_out, wait, hours = shots.plan(sb)
    todo = narration.stale(sb, lang)
    return {"problems": narration.text_problems(sb, lang), "length": round(narration.estimate_s(sb, lang)), "voice_calls": narration.calls_needed(sb, lang, todo),
            "engine": narration.engine(sb, lang), "addis_key": bool(os.environ.get("ADDIS_API_KEY", "").strip()),
            "plan": {"clips": [f"{s['id']}_{r}" for s, r in chosen], "left_out": len(left_out), "waiting": len(wait), "hours": round(hours, 1)},
            "storyboard": sb, "main": p.name == "storyboard.json", "rows": rows, "references": refs, "scores": scores, "gpu_jobs": gpu_jobs,
            "film": {r: url(folder / f"film_{r}.mp4") for r in keyframes.SIZES}, "radio_latest": url(max((folder / n for n in ("radio_cut.mp4", "radio_cut_partial.mp4")), key=lambda f: f.stat().st_mtime if f.exists() else 0)),
            "report": json.loads(report.read_text(encoding="utf-8")) if report.exists() else None,
            "feedback": [json.loads(x) for x in fb.read_text(encoding="utf-8").splitlines() if x.strip()] if fb.exists() else [],
            "locked": bool(sb["people"].get("based_on_real_people") and sb["people"].get("consent") != "recorded")}


def feedback_path(fid):
    mine = config.FILMS / fid
    return mine / "feedback.jsonl" if (mine / "storyboard.json").is_file() else config.ROOT / "feedback" / f"{fid}.jsonl"


# ---------------------------------------------------------------- limits, estimated from our own log

def limits():
    return {"tts": budget.tts_used(), "tts_free": budget.TTS_PER_DAY, "tts_reset": budget.tts_reset().isoformat(), "flux_used": budget.flux_used(),
            "flux_free": budget.FLUX_PER_DAY, "flux_reset": budget.flux_reset().isoformat(), "gpu_used_h": round(budget.gpu_used_h(), 2), "gpu_free_h": budget.GPU_H_PER_WEEK}


# ---------------------------------------------------------------- jobs

ACTIONS = {
    "voice": "Making voices", "references": "Drawing characters", "pictures": "Drawing pictures", "radio": "Building the radio cut",
    "motion_submit": "Sending clips to the GPU", "motion_status": "Checking the GPU", "motion_fetch": "Collecting clips",
    "pictures_submit": "Sending pictures to the GPU", "pictures_status": "Checking the GPU", "pictures_fetch": "Collecting pictures", "voice_submit": "Sending voices to the GPU", "voice_fetch": "Collecting voices", "music_submit": "Sending music to the GPU", "music_status": "Checking the GPU", "music_fetch": "Collecting music", "build": "Editing the film"}


def command(sb, action, body):
    ids = {s["id"] for s in sb["shots"]}
    only = [x for x in body.get("shots", []) if isinstance(x, str)]
    if any(x not in ids for x in only):
        raise Refused("Unknown shot.")
    ratios = [x for x in body.get("ratios", []) if isinstance(x, str)]
    if any(x not in keyframes.SIZES for x in ratios):
        raise Refused("Unknown format.")
    name = body.get("name")
    if name is not None and name not in sb["references"]:
        raise Refused("Unknown character.")
    pick = [y for x in only for y in ("--shot", x)]
    size = [y for x in ratios for y in ("--ratio", x)]
    force = ["--force"] if body.get("force") is True else []
    if action == "references":
        if not name:
            raise Refused("Choose a character.")
        parent = sb["references"][name].get("from")
        if parent and sb["references"][parent]["reason"] == "Not chosen yet":
            raise Refused(f"Choose the {parent} first; this one is drawn from that picture.")
        return ["references", "--name", name, *force]
    if action == "pictures":
        waiting = sorted({n for s in sb["shots"] if not only or s["id"] in only for n in s["references"] if sb["references"][n]["reason"] == "Not chosen yet"})
        if waiting:
            raise Refused("Choose these characters first: " + ", ".join(waiting))
        return ["keyframes", *(pick or [y for s in sb["shots"] for y in ("--shot", s["id"])]), *size, *force]
    return {"voice": ["narration", *pick, *force], "radio": ["radio", "--partial"], "build": ["assemble"],
            "pictures_submit": ["gpu", "submit", "pictures", *size, *pick], "pictures_status": ["gpu", "status", "pictures"], "pictures_fetch": ["gpu", "fetch", "pictures"],
            "voice_submit": ["gpu", "submit", "voice"], "voice_fetch": ["gpu", "fetch", "voice"],
            "motion_submit": ["gpu", "submit", "wan", *size, *pick], "motion_status": ["gpu", "status", "wan"], "motion_fetch": ["gpu", "fetch", "wan"],
            "music_submit": ["gpu", "submit", "music"], "music_status": ["gpu", "status", "music"], "music_fetch": ["gpu", "fetch", "music"]}[action]


def running():
    return bool(job) and job["proc"].poll() is None


def start(fid, action, body):
    if action not in ACTIONS:
        raise Refused("Unknown action.")
    with lock:
        if running():
            raise Refused("Something is already running. Wait for it to finish, or stop it.")
        p, sb = open_board(fid)
        errors = validate(sb)
        if errors:
            raise Refused("The storyboard has a problem: " + errors[0])
        if sb["people"].get("based_on_real_people") and sb["people"].get("consent") != "recorded" and action not in ("motion_status", "music_status", "pictures_status"):
            raise Refused("This is a true story. Record consent on the Story page first.")
        if action in ("motion_submit", "music_submit", "voice_submit", "pictures_submit") and body.get("replace") is not True:
            f = out(sb, "jobs", {"motion": "wan"}.get(action.split("_")[0], action.split("_")[0]) + ".json")
            if f.exists() and "done" not in json.loads(f.read_text(encoding="utf-8")).get("logged", []):
                raise Refused("An earlier GPU job has not been collected yet. Collect it first, or send again and lose it.")
        folder = out(sb)
        folder.mkdir(parents=True, exist_ok=True)
        log = folder / "web.log"
        with log.open("w", encoding="utf-8") as f:
            proc = subprocess.Popen([sys.executable, "-u", "-X", "utf8", "-m", "pipeline", "-s", str(p), *command(sb, action, body)],
                                    cwd=config.ROOT, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        job.clear()
        job.update(proc=proc, film=fid, action=action, label=ACTIONS[action], log=log, started=time.time())


def job_state():
    with lock:
        if not job:
            return {"running": False, "log": "", "label": None, "planned": plan_state()}
        text = job["log"].read_text(encoding="utf-8", errors="replace")[-5000:] if job["log"].exists() else ""
        code = job["proc"].poll()
        return {"running": code is None, "ok": code == 0, "label": job["label"], "action": job["action"], "film": job["film"],
                "planned": plan_state(), "stopped": job.get("stopped", False), "seconds": round(time.time() - job["started"]), "log": runlog.redact(text)}


def plan_state():
    return [{k: p[k] for k in ("film", "action", "label", "at")} for p in sorted(planned.values(), key=lambda p: p["at"])]


def plan_later(fid, body):
    """Start jobs when a free limit resets, one after another. They live in this window only: closing the studio cancels them."""
    action = body.get("action")
    reset = {"voice": budget.tts_reset, "pictures": budget.flux_reset, "references": budget.flux_reset}.get(action)
    if not reset:
        raise Refused("Only voices and pictures wait for a reset.")
    command(open_board(fid)[1], action, body)  # refuses a bad request now rather than at night
    at, key = reset() + timedelta(minutes=2), f"{action} {body.get('name', '')}"

    def go():
        with lock:
            if key not in planned:
                return
            if running():
                return again(30)
            planned.pop(key)
        try:
            start(fid, action, body)
        except config.PipelineError as e:
            print("planned job did not start:", e)

    def again(seconds):
        t = threading.Timer(seconds, go)
        t.daemon = True
        planned[key]["timer"] = t
        t.start()
    with lock:
        if key in planned:
            planned.pop(key)["timer"].cancel()
        planned[key] = {"film": fid, "action": action, "label": ACTIONS[action], "at": at.isoformat()}
        again((at - datetime.now(timezone.utc)).total_seconds())


def cancel_plan():
    with lock:
        for p in planned.values():
            p["timer"].cancel()
        planned.clear()


def stop():
    with lock:
        if running():
            job["stopped"] = True
            job["proc"].terminate()


# ---------------------------------------------------------------- edits

def edit(fid, body):
    """Apply one set of edits. Anything that would break the contract is refused and nothing is saved."""
    with lock:
        if running() and job["film"] == fid:
            raise Refused("Wait for the running job to finish before editing.")
        p, sb = open_board(fid)
        before = json.dumps(sb, sort_keys=True)
        by_id = {s["id"]: s for s in sb["shots"]}
        for sid, change in (body.get("shots") or {}).items():
            if sid not in by_id:
                raise Refused("Unknown shot.")
            s = by_id[sid]
            for k, v in change.items():
                if k == "narration":
                    s["narration"].update({x: str(t).strip() for x, t in v.items() if x in sb["voices"]})
                elif k == "transition":
                    s["transition"] = {"type": v["type"], "reason": str(v.get("reason") or "Chosen in the studio"),
                                       **({} if v["type"] == "cut" else {"seconds": (s.get("transition") or {}).get("seconds", 0.6)})}
                elif k in ("emotion", "voice_emotion") and not str(v).strip():
                    s.pop(k, None)
                elif k == "redraw" and v in keyframes.SIZES:
                    new_take(s, v)
                elif k in EDIT_SHOT:
                    s[k] = v if k == "seed" else str(v).strip()
                else:
                    raise Refused(f"{k} cannot be edited here.")
        for name, c in (body.get("references") or {}).items():
            if name not in sb["references"]:
                raise Refused("Unknown character.")
            choose_face(sb, name, c["seed"], str(c.get("reason") or "Chosen by the filmmaker in the studio"))
        if "music" in body:
            sb["music"].update(chosen_seed=body["music"]["seed"], reason=str(body["music"].get("reason") or "Chosen by the filmmaker in the studio"))
        if "voice" in body:
            set_voice(sb, body["voice"])
        for kind, names in (body.get("approve") or {}).items():
            approve(sb, kind, names, body.get("value") is not False)
        if "consent" in body:
            text = str(body["consent"]).strip()
            if len(text.split()) < 8:
                raise Refused("Please write who agreed, when, how and to what.")
            sb["people"].update(consent="recorded", consent_record=text)
        if json.dumps(sb, sort_keys=True) != before:
            sb["version"] += 1
            save_board(p, sb)


def new_take(shot, ratio):
    """Another take of one format only."""
    takes = shot.setdefault("takes", {})
    takes[ratio] = takes.get(ratio, 0) + 1


def choose_face(sb, name, seed, reason):
    ref = sb["references"][name]
    changed = ref["chosen_seed"] != seed
    ref.update(chosen_seed=seed, reason=reason)
    if changed:  # older versions are drawn from this face, so they must be drawn and chosen again
        for other in sb["references"].values():
            if other.get("from") == name:
                other["reason"] = "Not chosen yet"


def set_voice(sb, v):
    """Choose who speaks. A film uses one service; switching it makes every line out of date."""
    lang = sb["language"]
    if v["engine"] not in narration.ENGINES:
        raise Refused("Unknown voice service.")
    now = sb["voices"][lang]
    now["engine"] = v["engine"]
    now["voice"] = str(v["narrator"]).strip()
    for name, voice in (v.get("characters") or {}).items():
        if name not in now.get("characters", {}):
            raise Refused("Unknown character.")
        now["characters"][name]["voice"] = str(voice).strip()
    if v["engine"] != "gemini":
        for s in sb["shots"]:
            s.pop("tts_model", None)


def approve(sb, kind, names, yes):
    by_id = {s["id"]: s for s in sb["shots"]}
    lang = sb["language"]
    sb.setdefault("approvals", {})
    for name in names:
        sid, _, ratio = name.partition("_")
        s = by_id[sid]
        if not yes:
            sb["approvals"].get(kind, {}).pop(name, None)
            continue
        if kind == "script":
            approvals.give(sb, kind, sid, approvals.script_key(s))
        elif kind == "voice":
            key = narration.approval_key(sb, s, lang)
            if not key:
                raise Refused(f"{sid} has no current voice.")
            approvals.give(sb, kind, sid, key)
        elif kind == "picture" and ratio in keyframes.SIZES:
            p = keyframes.path(sb, s, ratio)
            if not cache.fresh(p, keyframes.inputs(sb, s, ratio)):
                raise Refused(f"{name} has no current picture.")
            approvals.give(sb, kind, name, cache.file_sha(p))
        else:
            raise Refused("Unknown approval.")


def restore(fid, body):
    with lock:
        if running():
            raise Refused("Wait for the running job to finish.")
        _, sb = open_board(fid)
        s = next((s for s in sb["shots"] if s["id"] == body.get("shot")), None)
        if not s or body.get("ratio") not in keyframes.SIZES:
            raise Refused("Unknown shot.")
        keyframes.restore(sb, s, body["ratio"], str(body.get("name")))


def add_feedback(fid, body):
    open_board(fid)
    row = {k: str(body.get(k, "")).strip() for k in ("test", "who", "words", "change")}
    if not row["who"] or not row["words"]:
        raise Refused("Write who the person is (no names) and what they said.")
    p = feedback_path(fid)
    p.parent.mkdir(exist_ok=True)
    with lock, p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row}, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def send(self, body, code=200, kind="text/html; charset=utf-8", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, data, code=200):
        self.send(json.dumps(data, ensure_ascii=False).encode("utf-8"), code, "application/json; charset=utf-8", [("Cache-Control", "no-store")])

    def allowed(self):
        """Refuse other sites posting to this page, and DNS rebinding."""
        hosts = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (origin is None or urlparse(origin).netloc in hosts)

    def media(self, rel):
        fid, _, inside = rel.partition("/")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", fid):
            return self.json({"error": "Not found"}, 404)
        home = root(fid).resolve()
        path = (home / inside).resolve()
        if home not in path.parents or path.suffix not in MEDIA or not path.is_file():
            return self.json({"error": "Not found"}, 404)
        size, first, last = path.stat().st_size, 0, path.stat().st_size - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m[1] or m[2]):
            first = int(m[1]) if m[1] else max(0, size - int(m[2]))
            last = min(last, int(m[2])) if m[1] and m[2] else last
            if first > last:
                return self.send(b"", 416, extra=[("Content-Range", f"bytes */{size}")])
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(last - first + 1))
        self.send_header("Accept-Ranges", "bytes")
        if m:
            self.send_header("Content-Range", f"bytes {first}-{last}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as f:
            f.seek(first)
            left = last - first + 1
            try:
                while left > 0 and (chunk := f.read(min(1 << 18, left))):
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except OSError:
                self.close_connection = True  # the browser stopped reading, for example when seeking

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self.allowed():
            return self.json({"error": "Forbidden"}, 403)
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/":
                return self.send((STATIC / "index.html").read_bytes())
            if path in ("/app.js", "/style.css"):
                return self.send((STATIC / path[1:]).read_bytes(), kind=("text/javascript" if path.endswith("js") else "text/css") + "; charset=utf-8", extra=[("Cache-Control", "no-cache")])
            if path == "/icon.svg":
                return self.send((config.ROOT / "assets" / "icon.svg").read_bytes(), kind="image/svg+xml")
            if path == "/font.ttf":
                return self.send(config.FONT.read_bytes(), kind="font/ttf")
            if path.startswith("/files/"):
                return self.media(path[7:])
            if path == "/api/films":
                return self.json([{"id": i, "title": json.loads(p.read_text(encoding="utf-8"))["title"], "main": p.name == "storyboard.json"} for i, p in index().items()])
            if path == "/api/options":
                return self.json({"languages": script.LANGUAGES, "soon": script.COMING_SOON, "themes": script.THEMES})
            if path == "/geist.ttf":
                return self.send((config.ROOT / "assets" / "fonts" / "Geist.ttf").read_bytes(), kind="font/ttf")
            if path == "/api/voices/gemini":
                return self.json([{"id": n, "name": n, "gender": g} for n, g in GEMINI_VOICES])
            if m := re.fullmatch(r"/api/voices/addis/([a-z]{2,3})", path):
                return self.json(providers.addis_voices(m[1]))
            if path == "/api/job":
                return self.json(job_state())
            if path == "/api/limits":
                return self.json(limits())
            if m := re.fullmatch(r"/api/film/([a-z0-9-]+)", path):
                return self.json(film_state(m[1]))
        except config.PipelineError as e:
            return self.json({"error": runlog.redact(str(e))[:400]}, 400)
        self.json({"error": "Not found"}, 404)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        kind = (self.headers.get("Content-Type") or "").split(";")[0]
        if not self.allowed() or size > 200_000 or kind != "application/json":
            self.close_connection = True
            return self.json({"error": "Forbidden"}, 403)
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(body, dict):
                raise ValueError
            if self.path == "/api/draft":
                args = (str(body.get(k, "")).strip() for k in ("story", "language", "theme", "audience", "intent"))
                return self.json({"id": script.new(*args, true_story=body.get("true_story") is True, consent_record=str(body.get("consent") or ""), narrator=body.get("narrator") if body.get("narrator") in ("man", "woman") else "man")[1]["id"]})
            if self.path == "/api/plan/cancel":
                cancel_plan()
                return self.json({"ok": True})
            if self.path == "/api/job/stop":
                stop()
                return self.json({"ok": True})
            m = re.fullmatch(r"/api/film/([a-z0-9-]+)/(run|edit|feedback|later|restore)", self.path)
            if not m:
                return self.json({"error": "Not found"}, 404)
            if m[2] == "run":
                start(m[1], body.get("action"), body)
            else:
                {"edit": edit, "feedback": add_feedback, "later": plan_later, "restore": restore}[m[2]](m[1], body)
            self.json({"ok": True})
        except config.PipelineError as e:
            self.json({"error": runlog.redact(str(e))[:600]}, 400)
        except (ValueError, KeyError, TypeError, AttributeError):
            self.json({"error": "That request was not understood."}, 400)

    def log_message(self, *a):
        pass


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Open http://localhost:{PORT} in your browser. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
