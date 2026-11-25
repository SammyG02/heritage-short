"""Moving-shot stage: a Wan clip if a matching one exists, otherwise a Ken Burns move on the keyframe."""
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


def wan_inputs(sb, shot, ratio):
    kf = keyframes.path(sb, shot, ratio)
    return {"stage": "wan/1", "model": sb["models"]["video"], "size": list(WAN_SIZE[ratio]), "seed": shot["seed"],
            "motion_prompt": motion(shot), **{k: v for k, v in sb["video"].items() if k != "max_gpu_hours"},  # a limit, not a setting of the clip
            "keyframe": cache.file_sha(kf) if kf.exists() else "missing"}


def has_wan(sb, shot, ratio):
    return cache.fresh(wan_path(sb, shot, ratio), wan_inputs(sb, shot, ratio))


def importance(shot, ratio):
    """Faces that speak first, then people, then close shots; the vertical film before the wide one."""
    return (4 * bool(shot.get("quote_voice")) + 2 * bool(shot["references"]) + (shot["size"] in ("close-up", "medium close-up", "medium"))
            + 8 * (ratio == "9x16"))


def plan(sb, ratios=("9x16", "16x9"), only=None, hours=None):
    """Which clips to make now. Returns (chosen, left out because of the limit, waiting for approval, hours needed)."""
    wait, want = [], []
    for ratio in ratios:
        for s in sb["shots"]:
            if (only and s["id"] not in only) or s.get("motion", "clip") == "camera" or has_wan(sb, s, ratio):
                continue
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


def make(sb, shot, ratio, lang, frames, force=False):
    """Render one shot at exactly `frames` frames. Returns (path, 'wan' or 'ken_burns')."""
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
        clip = sb["video"]["frames"] / 24 - 2 * TRIM_S
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
