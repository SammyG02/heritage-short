"""Command line: python -m pipeline <command>"""
import argparse
import sys
import time
from pathlib import Path

from . import assemble, gpu, keyframes, narration, script, shots, smoke
from .core import config, runlog, storyboard

GPU_WAIT_S = 4 * 3600


def film(sb, lang, use_gpu):
    print("1/5 narration")
    narration.run(sb, lang)
    print("2/5 keyframes")
    keyframes.run_references(sb)
    keyframes.run(sb)
    if use_gpu:
        print("3/5 moving shots and 4/5 music on Kaggle")
        submitted = {"wan": gpu.submit_wan(sb), "music": gpu.submit_music(sb)}
        for kind, kernel in submitted.items():
            if not kernel:
                continue
            deadline = time.time() + GPU_WAIT_S
            while (state := gpu.status(sb, kind)) in ("queued", "running", "unknown") and time.time() < deadline:
                print(f"  {kind}: {state}", flush=True)
                time.sleep(60)
            if state in ("queued", "running", "unknown"):
                print(f"  {kind}: still {state}; continuing with the fallback. Later: python -m pipeline gpu fetch {kind}")
                continue
            try:
                gpu.fetch(sb, kind)
            except config.PipelineError as e:
                print(f"  {kind}: {e}\n  continuing with the fallback")
    else:
        print("3/5 moving shots and 4/5 music from cache (add --gpu to generate missing ones on Kaggle)")
    print("5/5 assembly")
    assemble.film(sb, lang)


def status(sb, langs):
    """What a run would regenerate, without calling any model."""
    from .core import cache
    for lang in langs:
        stale = [s["id"] for s in sb["shots"] if not cache.fresh(narration.path(sb, s, lang), narration.inputs(sb, s, lang))]
        print(f"narration {lang}: {', '.join(stale) or 'all cached'}")
    for ratio in keyframes.SIZES:
        stale = [s["id"] for s in sb["shots"] if not cache.fresh(keyframes.path(sb, s, ratio), keyframes.inputs(sb, s, ratio))]
        print(f"keyframes {ratio}: {', '.join(stale) or 'all cached'}")
        stale = [s["id"] for s in sb["shots"] if not shots.has_wan(sb, s, ratio)]
        print(f"wan clips {ratio}: {'Ken Burns for ' + ', '.join(stale) if stale else 'all cached'}")
    for kind in ("wan", "music"):
        print(f"kaggle {kind}: {gpu.status(sb, kind)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m pipeline", description="Turn a storyboard into a narrated short film.")
    ap.add_argument("-s", "--storyboard", default=str(config.ROOT / "storyboard.json"), type=Path)
    ap.add_argument("-l", "--language", choices=list(script.LANGUAGES), help="default: the storyboard's main language")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("film", help="run every stage and export both formats")
    f.add_argument("--gpu", action="store_true", help="generate missing Wan clips and music on Kaggle, and wait")
    sub.add_parser("new", help="draft a storyboard from a story, language and theme")
    sub.add_parser("web", help="the same questions in a local web page")
    sub.add_parser("validate", help="check the storyboard")
    sub.add_parser("smoke", help="call each provider once")
    sub.add_parser("status", help="show what is stale")
    sub.add_parser("radio", help="narration over placeholder music on black")
    sub.add_parser("references", help="reference sheet only")
    sub.add_parser("keyframes", help="keyframes only")
    sub.add_parser("narration", help="narration only")
    g = sub.add_parser("gpu", help="Kaggle jobs")
    g.add_argument("action", choices=["submit", "status", "fetch"])
    g.add_argument("kind", choices=["wan", "music"])
    g.add_argument("--ratio", choices=list(keyframes.SIZES), action="append")
    g.add_argument("--shot", action="append")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        if a.cmd == "smoke":
            return 1 if smoke.run() else 0
        if a.cmd == "new":
            p, _ = script.interactive()
            print(f"\nDraft saved: {p}\nRead and edit it, then run: python -m pipeline -s {p} film")
            return 0
        if a.cmd == "web":
            from . import web
            web.serve()
            return 0
        sb = storyboard.load(a.storyboard)
        lang = a.language or sb["language"]
        if lang not in sb["voices"]:
            raise config.PipelineError(f"This storyboard has no {lang!r} narration.")
        if a.cmd == "validate":
            print(f"OK: {len(sb['shots'])} shots, languages {', '.join(sb['voices'])}")
        elif a.cmd == "film":
            film(sb, lang, a.gpu)
        elif a.cmd == "status":
            status(sb, list(sb["voices"]))
        elif a.cmd == "narration":
            narration.run(sb, lang)
        elif a.cmd == "radio":
            narration.run(sb, lang)
            assemble.radio(sb, lang)
        elif a.cmd == "references":
            keyframes.run_references(sb)
        elif a.cmd == "keyframes":
            keyframes.run_references(sb)
            keyframes.run(sb)
        elif a.cmd == "gpu":
            if a.action == "submit":
                gpu.submit_wan(sb, a.ratio or list(keyframes.SIZES), a.shot) if a.kind == "wan" else gpu.submit_music(sb)
            elif a.action == "status":
                print(gpu.status(sb, a.kind))
            else:
                gpu.fetch(sb, a.kind)
        return 0
    except config.PipelineError as e:
        print("ERROR: " + runlog.redact(str(e)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
