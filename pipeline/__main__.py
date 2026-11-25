"""Command line: python -m pipeline <command>"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import assemble, gpu, keyframes, narration, script, shots, smoke
from .core import approvals, cache, config, runlog, storyboard

GPU_WAIT_S = 4 * 3600


def film(sb, lang, use_gpu):
    print("1/5 narration")
    narration.run(sb, lang)
    print("2/5 keyframes")
    keyframes.run_references(sb)
    keyframes.run(sb)
    missing(sb, lang)  # nothing below may start, or spend GPU time, on an incomplete or out-of-date film
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


def approve(path, sb, kind, only, ratios):
    for s in sb["shots"]:
        if only and s["id"] not in only:
            continue
        if kind == "script":
            approvals.give(sb, kind, s["id"], approvals.script_key(s))
        elif kind == "voice":
            key = narration.approval_key(sb, s, sb["language"])
            if not key:
                print(f"  {s['id']}: no current voice to approve")
                continue
            approvals.give(sb, kind, s["id"], key)
        else:
            for r in ratios or keyframes.SIZES:
                p = keyframes.path(sb, s, r)
                if not cache.fresh(p, keyframes.inputs(sb, s, r)):
                    print(f"  {p.stem}: no current picture to approve")
                    continue
                approvals.give(sb, kind, p.stem, cache.file_sha(p))
    path.write_text(json.dumps(sb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"  approved {kind}: {', '.join(sorted(sb['approvals'].get(kind, {}))) or 'none'}")


def missing(sb, lang):
    """Stop before editing if any voice or picture is missing or out of date."""
    gaps = [f"voice {s['id']}" for s in sb["shots"] if not cache.fresh(narration.path(sb, s, lang), narration.inputs(sb, s, lang))]
    gaps += [f"picture {s['id']} {r}" for s in sb["shots"] for r in keyframes.SIZES
             if not cache.fresh(keyframes.path(sb, s, r), keyframes.inputs(sb, s, r))]
    if gaps:
        raise config.PipelineError(f"Not ready to edit, {len(gaps)} missing: " + ", ".join(gaps[:12]) + ("..." if len(gaps) > 12 else ""))


def status(sb, langs):
    """What a run would regenerate, without calling any model."""
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
    f.add_argument("--review", action="store_true", help="stop wherever a person has not approved the script, voice or picture")
    f.add_argument("--gpu", action="store_true", help="generate missing Wan clips and music on Kaggle, and wait")
    sub.add_parser("new", help="draft a storyboard from a story, language and theme")
    sub.add_parser("web", help="the same questions in a local web page")
    sub.add_parser("validate", help="check the storyboard")
    sub.add_parser("smoke", help="call each provider once")
    sub.add_parser("status", help="show what is stale")
    rd = sub.add_parser("radio", help="narration over placeholder music on black")
    rd.add_argument("--partial", action="store_true", help="call no model; show lines that have no voice yet as text")
    rf = sub.add_parser("references", help="reference sheet only")
    rf.add_argument("--name", action="append")
    kf = sub.add_parser("keyframes", help="keyframes only")
    kf.add_argument("--shot", action="append")
    kf.add_argument("--ratio", choices=list(keyframes.SIZES), action="append")
    na = sub.add_parser("narration", help="narration only")
    na.add_argument("--shot", action="append")
    for x in (rf, kf, na):
        x.add_argument("--force", action="store_true", help="make again even if cached")
    sub.add_parser("assemble", help="edit the film from what exists; calls no model")
    ap_ = sub.add_parser("approve", help="approve a step so the next one unlocks")
    ap_.add_argument("kind", choices=["script", "voice", "picture"])
    ap_.add_argument("--shot", action="append")
    ap_.add_argument("--ratio", choices=list(keyframes.SIZES), action="append")
    sub.add_parser("check", help="check the script for length, limits and unreadable text; calls no model")
    sub.add_parser("proof", help="one text call: proofread the narration")
    g = sub.add_parser("gpu", help="Kaggle jobs")
    g.add_argument("action", choices=["plan", "submit", "status", "fetch"])
    g.add_argument("kind", choices=["wan", "music", "voice", "pictures"])
    g.add_argument("--ratio", choices=list(keyframes.SIZES), action="append")
    g.add_argument("--shot", action="append")
    g.add_argument("--hours", type=float, help="most GPU hours to plan for")
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
        if config.FILMS.resolve() in a.storyboard.resolve().parents:
            runlog.use_private()
        lang = a.language or sb["language"]
        if lang not in sb["voices"]:
            raise config.PipelineError(f"This storyboard has no {lang!r} narration.")
        if a.cmd == "film" and not a.review:
            approvals.no_review()
        if a.cmd == "validate":
            print(f"OK: {len(sb['shots'])} shots, languages {', '.join(sb['voices'])}")
        elif a.cmd == "film":
            film(sb, lang, a.gpu)
        elif a.cmd == "status":
            status(sb, list(sb["voices"]))
        elif a.cmd == "narration":
            narration.run(sb, lang, a.force, a.shot)
        elif a.cmd == "assemble":
            missing(sb, lang)
            assemble.film(sb, lang)
        elif a.cmd == "radio":
            silent = ()
            if a.partial:
                silent = [s["id"] for s in sb["shots"] if not cache.fresh(narration.path(sb, s, lang), narration.inputs(sb, s, lang))]
            else:
                narration.run(sb, lang)
            assemble.radio(sb, lang, silent)
        elif a.cmd == "references":
            keyframes.run_references(sb, a.force, a.name)
        elif a.cmd == "keyframes":
            if not a.shot:
                keyframes.run_references(sb)
            keyframes.run(sb, a.ratio or tuple(keyframes.SIZES), a.force, a.shot)
        elif a.cmd == "approve":
            approve(a.storyboard, sb, a.kind, a.shot, a.ratio)
        elif a.cmd == "check":
            notes = narration.text_problems(sb, lang)
            todo = narration.stale(sb, lang)
            print("\n".join(notes) or "No text problems found.")
            print(f"About {narration.estimate_s(sb, lang):.0f} s (must be 60-90). {len(todo)} lines without a voice, {narration.calls_needed(sb, lang, todo)} voice calls at best.")
        elif a.cmd == "proof":
            for n in script.proofread(sb, lang):
                print(f"{n.get('shot')}: {n.get('problem')}\n    {n.get('suggestion')}")
        elif a.cmd == "gpu":
            if a.action == "plan":
                chosen, left_out, wait, hours = shots.plan(sb, a.ratio or list(keyframes.SIZES), a.shot, a.hours)
                name = lambda xs: ", ".join(f"{s['id']}_{r}" for s, r in xs) or "none"  # noqa: E731
                print(f"now ({hours:.1f} h): {name(chosen)}\nleft out by the limit: {name(left_out)}\nwaiting for approval: {name(wait)}")
                return 0
            if a.action == "submit":
                gpu.submit_wan(sb, a.ratio or list(keyframes.SIZES), a.shot, a.hours) if a.kind == "wan" else gpu.submit_pictures(sb, a.ratio or list(keyframes.SIZES), a.shot) if a.kind == "pictures" else gpu.submit_voice(sb, lang) if a.kind == "voice" else gpu.submit_music(sb)
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
