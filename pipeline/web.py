"""A local page for people who do not use a terminal: tell a story, edit the draft, approve, get a film.

It only listens on this computer and only calls the same functions as the command line.
"""
import json
import re
import subprocess
import sys
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import script
from .core import config, runlog
from .core.storyboard import load, out, validate

PORT = 8765
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
jobs: dict[str, subprocess.Popen] = {}
lock = threading.Lock()

CSS = """
:root{--bg:#fbf6ee;--fg:#2a211c;--card:#fff;--line:#e2d5c3;--accent:#9a4a1f;--muted:#75665a}
@media(prefers-color-scheme:dark){:root{--bg:#1b171d;--fg:#f2e8da;--card:#262029;--line:#43394a;--accent:#e59a5c;--muted:#b5a79b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.55 system-ui,'Noto Sans Ethiopic',Ebrima,sans-serif}
main{max-width:760px;margin:auto;padding:32px 20px 80px}h1{font-size:2rem;margin:.2em 0}label{display:block;margin:22px 0 6px;font-weight:600}
textarea,input,select{width:100%;padding:12px;font:inherit;color:inherit;background:var(--card);border:1px solid var(--line);border-radius:10px}
.opts{display:flex;flex-wrap:wrap;gap:10px}.opts label{margin:0;font-weight:400;border:1px solid var(--line);background:var(--card);border-radius:10px;padding:10px 14px;display:flex;gap:8px;align-items:center}
.opts input{width:auto}.soon{opacity:.5}button{margin-top:28px;padding:14px 26px;font:inherit;font-weight:600;border:0;border-radius:10px;background:var(--accent);color:var(--bg);cursor:pointer}
button:disabled{opacity:.5}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.muted{color:var(--muted);font-size:.9rem}pre{white-space:pre-wrap;background:var(--card);border:1px solid var(--line);padding:14px;border-radius:10px;font-size:.85rem}
.err{border-left:4px solid #c0392b;padding:10px 14px;background:var(--card)}video{width:100%;max-height:70vh;border-radius:12px;background:#000}
"""


def page(title, body):
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{CSS}</style><main>{body}</main></html>").encode("utf-8")


def form(error="", v=None):
    v = v or {}
    langs = "".join(f"<label><input type=radio name=language value={k} {'checked' if v.get('language', 'am') == k else ''}>{n}</label>"
                    for k, n in script.LANGUAGES.items())
    langs += "".join(f"<label class=soon><input type=radio disabled>{n} (coming soon)</label>" for n in script.COMING_SOON)
    themes = "".join(f"<option value={k}>{escape(t)}</option>" for k, t in script.THEMES.items())
    return page("Tell your story", f"""<h1>Tell your story</h1>
<p class=muted>Write it the way you would tell it. Please leave out real names and private details: the text is sent to a free AI service
that may learn from it. The film uses invented characters, never real faces or voices.</p>
{f'<p class=err role=alert>{escape(error)}</p>' if error else ''}
<form method=post action=/draft onsubmit="b.disabled=1;b.textContent='Writing your storyboard, up to a few minutes...'">
<label for=story>Your story</label><textarea id=story name=story rows=7 required>{escape(v.get('story', ''))}</textarea>
<label>Narration language</label><div class=opts>{langs}</div>
<label for=theme>Theme</label><select id=theme name=theme>{themes}</select>
<label for=audience>Who is it for?</label><input id=audience name=audience required value="{escape(v.get('audience', ''), True)}" placeholder="My cousins abroad">
<label for=intent>What should they feel at the end?</label><input id=intent name=intent required value="{escape(v.get('intent', ''), True)}" placeholder="Close to home">
<button id=b>Draft my storyboard</button></form>""")


def review(sb, error=""):
    cards = ""
    for s in sb["shots"]:
        boxes = "".join(f"<label for={s['id']}_{k}>{script.LANGUAGES[k]}</label><textarea id={s['id']}_{k} name={s['id']}_{k} rows=2 required>{escape(t)}</textarea>"
                        for k, t in s["narration"].items())
        cards += f"<div class=card><b>{s['id']}</b> <span class=muted>{escape(s['reason'])}</span><p class=muted>Picture: {escape(s['image_prompt'])}</p>{boxes}</div>"
    return page("Check your storyboard", f"""<h1>{escape(' / '.join(sb['title'].values()))}</h1><p>{escape(sb['logline'])}</p>
<p>Change any words that do not sound right. Nothing is generated until you approve.</p>{f'<p class=err role=alert>{escape(error)}</p>' if error else ''}
<form method=post action=/approve><input type=hidden name=id value={sb['id']}>{cards}<button>Approve and make the film</button></form>""")


def progress(sid):
    log = config.OUTPUTS / sid / "web.log"
    text = log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.exists() else "Starting..."
    proc = jobs.get(sid)
    running = proc is not None and proc.poll() is None
    sb = load(config.ROOT / "storyboards" / f"{sid}.json")
    film = out(sb, "film", sb["language"], "film_9x16.mp4")
    done = not running and film.exists() and (proc is None or proc.returncode == 0)
    head = "<meta http-equiv=refresh content=5><h1>Making your film</h1><p>This takes several minutes.</p>" if running else (
        f"<h1>Your film</h1><video controls src=/video/{sid}/9x16></video><p><a href=/video/{sid}/16x9>Wide version</a> · <a href=/>Tell another story</a></p>"
        if done else "<h1>The film stopped</h1><p>Progress is saved; running again continues from here.</p>"
        f"<form method=post action=/resume><input type=hidden name=id value={sid}><button>Try again</button></form>")
    return page("Your film", f"{head}<pre>{escape(runlog.redact(text))}</pre>")


def start(sid):
    with lock:
        if any(p.poll() is None for p in jobs.values()):
            raise config.PipelineError("Another film is being made. Please wait for it to finish.")
        folder = config.OUTPUTS / sid
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "web.log").open("w", encoding="utf-8") as log:
            jobs[sid] = subprocess.Popen([sys.executable, "-u", "-X", "utf8", "-m", "pipeline", "-s", str(config.ROOT / "storyboards" / f"{sid}.json"), "film"],
                                         cwd=config.ROOT, stdout=log, stderr=subprocess.STDOUT)


def board(sid):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,40}", sid or ""):
        raise config.PipelineError("Unknown storyboard.")
    p = config.ROOT / "storyboards" / f"{sid}.json"
    return p, load(p)


class Handler(BaseHTTPRequestHandler):
    def send(self, body, code=200, kind="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, to):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def allowed(self):
        """Refuse other sites posting to this page, and DNS rebinding."""
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in HOSTS and (origin is None or urlparse(origin).netloc in HOSTS)

    def do_GET(self):
        if not self.allowed():
            return self.send(b"Forbidden", 403)
        parts = urlparse(self.path).path.strip("/").split("/")
        try:
            if parts == [""]:
                return self.send(form())
            if parts[0] == "review":
                return self.send(review(board(parts[1])[1]))
            if parts[0] == "film":
                board(parts[1])
                return self.send(progress(parts[1]))
            if parts[0] == "video" and parts[2] in ("9x16", "16x9"):
                _, sb = board(parts[1])
                return self.send(out(sb, "film", sb["language"], f"film_{parts[2]}.mp4").read_bytes(), kind="video/mp4")
        except (config.PipelineError, OSError, IndexError):
            pass
        self.send(page("Not found", "<h1>Not found</h1><a href=/>Start</a>"), 404)

    def do_POST(self):
        size = int(self.headers.get("Content-Length") or 0)
        if not self.allowed() or size > 200_000:
            return self.send(b"Forbidden", 403)
        v = {k: x[0].strip() for k, x in parse_qs(self.rfile.read(size).decode("utf-8")).items()}
        try:
            if self.path == "/draft":
                try:
                    _, sb = script.new(*(v.get(k, "") for k in ("story", "language", "theme", "audience", "intent")))
                except config.PipelineError as e:
                    return self.send(form(runlog.redact(str(e))[:400], v), 400)
                return self.redirect(f"/review/{sb['id']}")
            p, sb = board(v.get("id"))
            if self.path == "/approve":
                for s in sb["shots"]:
                    for k in s["narration"]:
                        s["narration"][k] = v.get(f"{s['id']}_{k}", "")
                sb["status"] = "approved"
                errors = validate(sb)
                if errors:
                    return self.send(review(sb, "; ".join(errors)[:400]), 400)
                p.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            elif self.path != "/resume":
                return self.send(b"Not found", 404)
            start(sb["id"])
            self.redirect(f"/film/{sb['id']}")
        except config.PipelineError as e:
            self.send(page("Problem", f"<h1>Something went wrong</h1><p class=err>{escape(runlog.redact(str(e))[:400])}</p><a href=/>Start</a>"), 400)

    def log_message(self, *a):
        pass


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Open http://localhost:{PORT} in your browser. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
