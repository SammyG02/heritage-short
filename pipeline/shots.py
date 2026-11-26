"""Moving-shot stage: a Wan clip if a matching one exists, otherwise a Ken Burns move on the keyframe."""
import os
import re
import subprocess

from . import keyframes
from .core import approvals, budget, cache, config
from .core.storyboard import out

DELIVERY = {"9x16": (1080, 1920), "16x9": (1920, 1080)}
WAN_SIZE = {"9x16": (480, 832), "16x9": (832, 480)}
TRIM_S = 0.25  # weak first and last frames of generated clips


def wan_path(sb, shot, ratio):
    return out(sb, "shots", "wan", f"{shot['id']}_{ratio}.mp4")


def motion(shot):
    return shot["motion_prompt"] + (f". Emotion: {shot['emotion']}" if shot.get("emotion") else "")


# WaveSpeed Wan 2.2 at 480p, USD per second of clip; model pages, 26 Nov 2026. Clips are 5 or 8 seconds.
# Fast is listed at $0.01 a second but was charged $0.02: an 8 s and a 5 s clip took the balance from $1.00 to $0.74 (26 Nov 2026).
WAVESPEED = {"fast": ("wavespeed-ai/wan-2.2/i2v-480p-ultra-fast", 0.02), "standard": ("wavespeed-ai/wan-2.2/i2v-480p", 0.03)}
WAVE_LENGTHS = (5, 8)


def wave_model(sb):
    return sb.get("services", {}).get("wavespeed", "fast")


STRETCH = {"people": 1.25, "scenery": 1.6}  # how far a clip may be slowed before slow motion shows


def wave_seconds(sb, shot):
    """5 s unless slowing a 5 s clip to fill the shot would show: people up to 1.25x, scenery (no cast) up to 1.6x; then 8 s."""
    from . import narration
    v = narration.path(sb, shot, sb["language"])
    need = max(shot["duration_s"], (narration.seconds(v) + 0.6) if v.exists() else 0)
    return 5 if need <= 5 * STRETCH["people" if shot["references"] else "scenery"] else 8


def wave_cost(model, seconds):
    per = next(p for m, p in WAVESPEED.values() if m == model) if "/" in model else WAVESPEED[model][1]
    return round(per * seconds, 2)


def wave_price(sb, shot, quality=None):
    return wave_cost(quality or wave_model(sb), wave_seconds(sb, shot))


def animator(sb, shot=None):
    """Who makes this shot's clip: 'kaggle' (free GPU, the default) or 'wavespeed' (paid, minutes, a few shots only).
    WaveSpeed only with its key in .env: a film made elsewhere then falls back to the free GPU instead of never moving."""
    who = (shot or {}).get("animate") or sb.get("services", {}).get("animate", "kaggle")
    return who if who != "wavespeed" or os.environ.get("WAVESPEED_API_KEY", "").strip() else "kaggle"


def motion_seed(shot):
    """Animate again: a new take moves the clip's seed only; the picture keeps its own."""
    return shot["seed"] + 1000 * shot.get("takes", {}).get("clip", 0)


def wan_inputs(sb, shot, ratio, who=None, quality=None, seconds=None):
    kf = keyframes.path(sb, shot, ratio)
    frame = cache.file_sha(kf) if kf.exists() else "missing"
    if (who or animator(sb, shot)) == "wavespeed":
        return {"stage": "wan/1", "model": WAVESPEED[quality or wave_model(sb)][0], "seconds": seconds or wave_seconds(sb, shot), "seed": motion_seed(shot),
                "motion_prompt": motion(shot), "negative_prompt": sb["video"].get("negative_prompt", ""), "keyframe": frame}
    return {"stage": "wan/1", "model": sb["models"]["video"], "size": list(WAN_SIZE[ratio]), "seed": motion_seed(shot),
            "motion_prompt": motion(shot), **{k: v for k, v in sb["video"].items() if k != "max_gpu_hours"},  # a limit, not a setting of the clip
            "keyframe": frame}


def has_wan(sb, shot, ratio):
    """A clip from either animator counts, so switching service never throws a finished clip away."""
    p = wan_path(sb, shot, ratio)
    if cache.fresh(p, wan_inputs(sb, shot, ratio, "kaggle")):
        return True
    return any(cache.fresh(p, wan_inputs(sb, shot, ratio, "wavespeed", q, n)) for q in WAVESPEED for n in WAVE_LENGTHS)


def keep_clip(p):
    """The clip being replaced goes to versions/, so a worse new take never loses the old one."""
    if not p.exists():
        return
    old = p.parent / "versions"
    old.mkdir(exist_ok=True)
    n = len(list(old.glob(p.stem + "_*.mp4"))) + 1
    p.replace(old / f"{p.stem}_{n}.mp4")
    meta = cache.meta_path(p)
    if meta.exists():
        meta.replace(old / f"{p.stem}_{n}.mp4{meta.name[len(p.name):]}")


def seconds_of(p):
    """Length of a video, from FFmpeg's own report."""
    r = subprocess.run([config.ffmpeg(), "-i", str(p)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 3) if m else None


def importance(shot, ratio):
    """Faces that speak first, then people, then close shots; the vertical film before the wide one."""
    return (4 * bool(shot.get("quote_voice")) + 2 * bool(shot["references"]) + (shot["size"] in ("close-up", "medium close-up", "medium"))
            + 8 * (ratio == "9x16"))


def plan(sb, ratios=None, only=None, hours=None):
    """Which clips to make now. Returns (chosen, left out because of the limit, waiting for approval, hours needed)."""
    wait, want, ratios = [], [], ratios or keyframes.drawn(sb)
    for ratio in ratios:
        for s in sb["shots"]:
            if (only and s["id"] not in only) or s.get("motion", "clip") == "camera" or animator(sb, s) != "kaggle" or has_wan(sb, s, ratio):
                continue  # the Kaggle plan: WaveSpeed shots are sent by wavespeed.py
            p = keyframes.path(sb, s, ratio)
            ready = p.exists() and cache.fresh(p, keyframes.inputs(sb, s, ratio)) and approvals.ok(sb, "picture", p.stem, cache.file_sha(p))
            (want if ready else wait).append((s, ratio))
    want.sort(key=lambda x: -importance(*x))
    cap = min(hours if hours is not None else sb["video"].get("max_gpu_hours", 4), budget.gpu_left_h() - budget.GPU_RESERVE_H, budget.GPU_SESSION_H)
    fit = max(0, int((cap * 3600 - 300) // budget.clip_seconds()))  # 300 s to load the model
    chosen = want[:fit]
    return chosen, want[fit:], wait, (len(chosen) * budget.clip_seconds() + 300 * bool(chosen)) / 3600


def path(sb, shot, ratio, lang):
    return out(sb, "shots", "cut", lang, f"{shot['id']}_{ratio}.mp4")


def _zoompan(move, frames, w, h):
    t = f"on/{max(frames - 1, 1)}"
    z, x, y = "1.10", "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    if move == "in":
        z = f"1+0.12*{t}"
    elif move == "out":
        z = f"1.12-0.12*{t}"
    elif move in ("left", "right"):
        x = f"(iw-iw/zoom)*{t if move == 'right' else f'(1-{t})'}"
    else:
        y = f"(ih-ih/zoom)*{t if move == 'down' else f'(1-{t})'}"
    # Upscaling first hides zoompan's whole-pixel stepping.
    return (f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps=24,format=yuv420p")


def tail_frames(shot):
    """Extra frames the previous shot needs so it can still be seen while this one arrives."""
    t = shot.get("transition")
    return 0 if not t or t["type"] == "cut" else round(t.get("seconds", 0.6) * 24)


def from_vertical(sb, shot, lang, frames, force=False):
    """The wide shot made from the finished vertical one: the same frames, sharp in the middle,
    over a blurred and darkened copy that fills the sides. Calls no model."""
    tall, kind = make(sb, shot, "9x16", lang, frames, force)
    w, h = DELIVERY["16x9"]
    p = path(sb, shot, "16x9", lang)
    inp = {"stage": "wide-from-vertical/1", "kind": kind, "source": cache.file_sha(tall), "frames": frames, "size": [w, h]}
    if not force and cache.fresh(p, inp):
        return p, kind
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".part.mp4")
    # The blur is made small and scaled up: the same look, a fraction of the work.
    graph = (f"[0:v]split[a][b];[a]scale=480:270:force_original_aspect_ratio=increase,crop=480:270,boxblur=10:2,"
             f"eq=brightness=-0.12,scale={w}:{h}[bg];[b]scale=-2:{h}:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:0,format=yuv420p")
    config.run_ffmpeg(["-i", tall, "-filter_complex", graph, "-frames:v", frames, "-r", 24, "-c:v", "libx264",
                       "-preset", "veryfast", "-crf", 17, "-pix_fmt", "yuv420p", "-an", tmp])
    tmp.replace(p)
    cache.stamp(p, inp)
    print(f"  shot {shot['id']}_16x9 (from the vertical, {frames / 24:.1f}s)")
    return p, kind


def make(sb, shot, ratio, lang, frames, force=False):
    """Render one shot at exactly `frames` frames. Returns (path, 'wan' or 'ken_burns')."""
    if ratio not in keyframes.drawn(sb):
        return from_vertical(sb, shot, lang, frames, force)
    w, h = DELIVERY[ratio]
    p = path(sb, shot, ratio, lang)
    wan = has_wan(sb, shot, ratio)
    src = wan_path(sb, shot, ratio) if wan else keyframes.path(sb, shot, ratio)
    kind = "wan" if wan else "ken_burns"
    inp = {"stage": "cut/1", "kind": kind, "source": cache.file_sha(src), "frames": frames,
           "size": [w, h], "move": None if wan else shot["ken_burns"]}
    if not force and cache.fresh(p, inp):
        return p, kind
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.stem + ".part.mp4")
    enc = ["-frames:v", frames, "-r", 24, "-c:v", "libx264", "-preset", "veryfast", "-crf", 17, "-pix_fmt", "yuv420p", "-an", tmp]
    if wan:
        clip = (cache.read_meta(src).get("seconds") or sb["video"]["frames"] / 24) - 2 * TRIM_S  # WaveSpeed clips are 8 s
        slow = max(1.0, (frames / 24) / clip)
        vf = (f"trim=start={TRIM_S}:duration={clip},setpts={slow:.5f}*(PTS-STARTPTS),"
              + ("minterpolate=fps=24:mi_mode=blend," if slow > 1.01 else "")
              + f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h},"
              f"fps=24,tpad=stop_mode=clone:stop_duration=2,format=yuv420p")
        config.run_ffmpeg(["-i", src, "-vf", vf, *enc])
    else:
        config.run_ffmpeg(["-i", src, "-vf", _zoompan(shot["ken_burns"], frames, w, h), *enc])
    tmp.replace(p)
    cache.stamp(p, inp)
    print(f"  shot {shot['id']}_{ratio} ({kind}, {frames / 24:.1f}s)")
    return p, kind
