"""Assembly stage: timeline, subtitles, mix, loudness, end card and exports. FFmpeg only, no models."""
import json
import math
import re
import shutil
import textwrap

from PIL import Image, ImageDraw, ImageFont

from . import music, narration, shots
from .core import cache, config
from .core.storyboard import out

FPS, LEAD, TAIL = 24, 0.45, 0.65


def timeline(sb, lang):
    """Shot lengths follow the voice, then snap up to the score's beat so cuts land on it."""
    beat = 60 / sb["music"]["bpm"]
    t, rows = 0, []
    for shot in sb["shots"]:
        voice = narration.seconds(narration.path(sb, shot, lang))
        need = max(shot["duration_s"], LEAD + voice + TAIL)
        end = round(math.ceil((t / FPS + need) / beat - 1e-6) * beat * FPS)
        rows.append({"shot": shot, "start": t / FPS, "frames": end - t, "voice": voice})
        t = end
    total = t / FPS + sb["end_card"]["duration_s"]
    return rows, total


def _ts(s, sep=","):
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}{sep}{ms % 1000:03}"


def subtitles(sb, rows, width=38):
    """English lines, at most two per caption, timed by share of characters."""
    caps = []
    for r in rows:
        lines = textwrap.wrap(r["shot"]["narration"]["en"], width)
        groups = [lines[i:i + 2] for i in range(0, len(lines), 2)]
        chars = sum(len(" ".join(g)) for g in groups)
        t = r["start"] + LEAD
        for g in groups:
            d = (r["voice"] + 0.3) * len(" ".join(g)) / chars
            caps.append((t, t + d, g))
            t += d
    return caps


def write_subtitles(sb, caps, ratio, folder):
    srt = "\n".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n" + "\n".join(g) + "\n" for i, (a, b, g) in enumerate(caps, 1))
    (folder / "subtitles_en.srt").write_text(srt, encoding="utf-8", newline="\n")
    w, h = shots.DELIVERY[ratio]
    # Vertical captions sit above the area that phone apps cover with buttons.
    size, margin = (52, 420) if ratio == "9x16" else (50, 80)
    head = (f"[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
            f"Style: S,Noto Sans Ethiopic,{size},&H00F4F8FF,&H00101820,&H80000000,-1,1,3.5,1,2,60,60,{margin}\n\n[Events]\n"
            "Format: Layer, Start, End, Style, Text\n")

    def at(s):
        return _ts(s, ".")[1:-1]
    body = "".join(f"Dialogue: 0,{at(a)},{at(b)},S," + r"\N".join(g) + "\n" for a, b, g in caps)
    p = folder / f"subs_{ratio}.ass"
    p.write_text(head + body, encoding="utf-8", newline="\n")
    return p


def end_card(sb, ratio, folder):
    w, h = shots.DELIVERY[ratio]
    im = Image.new("RGB", (w, h), (24, 20, 30))
    d = ImageDraw.Draw(im)
    lines = sb["end_card"]["lines"]
    sizes = [int(min(w, h) * (0.085 if i == 0 else 0.055 if i == 1 else 0.042)) for i in range(len(lines))]
    y = h / 2 - sum(s * 1.7 for s in sizes) / 2
    for line, s in zip(lines, sizes):
        font = ImageFont.truetype(str(config.FONT), s)
        d.text((w / 2, y), line, font=font, fill=(246, 222, 180) if s == sizes[0] else (235, 232, 225), anchor="ma")
        y += s * 1.7
    p = folder / f"end_card_{ratio}.png"
    im.save(p)
    return p


def _loudnorm(stderr):
    return json.loads(re.findall(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr, re.S)[-1])


def measure(path):
    return _loudnorm(config.run_ffmpeg(["-i", path, "-vn", "-af", "loudnorm=print_format=json", "-f", "null", "-"]))


def _gain(path, target):
    return target - float(measure(path)["input_i"])


def mix(sb, lang, rows, total, folder, bed=None):
    """Voice on the timeline, music ducked under it, then two-pass loudness."""
    m = sb["mix"]
    score, kind = bed or music.score(sb)
    args, parts = [], []
    for i, r in enumerate(rows):
        p = narration.path(sb, r["shot"], lang)
        args += ["-i", p]
        ms = round((r["start"] + LEAD) * 1000)
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,volume={_gain(p, -18):.2f}dB,adelay={ms}[v{i}]")
    n = len(rows)
    args += ["-stream_loop", -1, "-i", score]
    marks = {c["action"]: next(r for r in rows if r["shot"]["id"] == c["shot"]) for c in sb["music"]["cues"]}
    vol = "1"
    if "lower" in marks:
        a = marks["lower"]["start"]
        b = marks["lift"]["start"] if "lift" in marks else a + marks["lower"]["frames"] / FPS
        vol = f"if(between(t,{a:.2f},{b:.2f}),0.25,1)"
    parts.append("".join(f"[v{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad=whole_dur={total:.3f},atrim=0:{total:.3f},asplit=2[voice][key]")
    parts.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.3f},volume={_gain(score, m['music_lufs']):.2f}dB,"
                 f"volume='{vol}':eval=frame,afade=t=in:d=0.6,afade=t=out:st={total - 2.5:.2f}:d=2.5[bed]")
    parts.append(f"[bed][key]sidechaincompress=threshold={m['duck_threshold']}:ratio={m['duck_ratio']}:attack={m['duck_attack_ms']}:release={m['duck_release_ms']}[ducked]")
    parts.append("[voice]aformat=channel_layouts=stereo[vs];[vs][ducked]amix=inputs=2:normalize=0[out]")
    pre = folder / "premix.wav"
    config.run_ffmpeg([*args, "-filter_complex", ";".join(parts), "-map", "[out]", "-ar", 48000, pre])
    target = f"I={m['target_lufs']}:TP={m['true_peak_db'] - 0.5}:LRA=11"
    a = _loudnorm(config.run_ffmpeg(["-i", pre, "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"]))
    final = folder / "mix.wav"
    config.run_ffmpeg(["-i", pre, "-af", f"loudnorm={target}:measured_I={a['input_i']}:measured_TP={a['input_tp']}:measured_LRA={a['input_lra']}"
                       f":measured_thresh={a['input_thresh']}:offset={a['target_offset']}:linear=true", "-ar", 48000, final])
    pre.unlink()
    return final, kind


def _folder(sb, lang):
    f = out(sb, "film", lang)
    f.mkdir(parents=True, exist_ok=True)
    return f


def check_length(total):
    if not 60 <= total <= 90:
        raise config.PipelineError(f"The film would be {total:.1f} s; it must be 60-90 s. Shorten or lengthen narration or durations.")


def radio(sb, lang):
    """Narration over placeholder music on a black screen."""
    folder = _folder(sb, lang)
    rows, total = timeline(sb, lang)
    audio, _ = mix(sb, lang, rows, total, folder, (music.placeholder(sb), "placeholder"))
    p = folder / "radio_cut.mp4"
    config.run_ffmpeg(["-f", "lavfi", "-i", f"color=black:s=720x1280:r=24:d={total:.3f}", "-i", audio, "-c:v", "libx264",
                       "-preset", "veryfast", "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-shortest", p])
    print(f"  radio cut {lang}: {total:.1f}s  {p}")
    return p


def film(sb, lang, ratios=("9x16", "16x9")):
    folder = _folder(sb, lang)
    rows, total = timeline(sb, lang)
    check_length(total)
    audio, kind = mix(sb, lang, rows, total, folder)
    caps = subtitles(sb, rows)
    work = folder / "work"
    results = []
    for ratio in ratios:
        work.mkdir(exist_ok=True)
        clips = [shots.make(sb, r["shot"], ratio, lang, r["frames"])[0] for r in rows]
        w, h = shots.DELIVERY[ratio]
        (work / "list.txt").write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
        card = end_card(sb, ratio, work)
        write_subtitles(sb, caps, ratio, work)
        shutil.copy(work / "subtitles_en.srt", folder / "subtitles_en.srt")
        shutil.copy(config.FONT, work / "font.ttf")
        body = sum(r["frames"] for r in rows) / FPS
        card_s = sb["end_card"]["duration_s"]
        graph = (f"[0:v]subtitles=subs_{ratio}.ass:fontsdir=.,fade=t=in:d=0.6,fade=t=out:st={body - 0.5:.3f}:d=0.5[a];"
                 f"[1:v]scale={w}:{h},fade=t=in:d=0.4,format=yuv420p,fps=24[b];[a][b]concat=n=2:v=1:a=0[v]")
        p = folder / f"film_{ratio}.mp4"
        config.run_ffmpeg(["-f", "concat", "-safe", 0, "-i", "list.txt", "-loop", 1, "-t", card_s, "-framerate", 24, "-i", card,
                           "-i", audio, "-filter_complex", graph, "-map", "[v]", "-map", "2:a", "-r", 24, "-c:v", "libx264",
                           "-preset", "medium", "-crf", 20, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", 48000,
                           "-movflags", "+faststart", "-t", f"{total:.3f}", "-metadata", "comment=Made with AI", p], cwd=work)
        results.append(p)
    shutil.rmtree(work)
    wan = {r: sum(shots.has_wan(sb, s, r) for s in sb["shots"]) for r in ratios}
    report = {"language": lang, "seconds": round(total, 2), "music": kind, "wan_shots": wan, "shots": len(sb["shots"]),
              "files": [verify(p, sb) for p in results],
              "timeline": [{"shot": r["shot"]["id"], "start": round(r["start"], 2), "seconds": round(r["frames"] / FPS, 2),
                            "voice": round(r["voice"], 2)} for r in rows]}
    (folder / "report.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"  film {lang}: {total:.1f}s, music {kind}, Wan shots {wan}")
    for f in report["files"]:
        print(f"    {f}")
    return results


def verify(p, sb):
    """Measure the finished file and fail if it misses the delivery targets."""
    info = config.run_ffmpeg(["-i", p, "-c", "copy", "-f", "null", "-"])
    hh, mm, ss = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
    secs = int(hh) * 3600 + int(mm) * 60 + float(ss)
    w, h = map(int, re.search(r"Video:.*?(\d{3,4})x(\d{3,4})", info).groups())
    fps = float(re.search(r"([\d.]+) fps", info).group(1))
    a = measure(p)
    lufs, tp = float(a["input_i"]), float(a["input_tp"])
    problems = []
    if not 60 <= secs <= 90:
        problems.append("length")
    if (w, h) not in shots.DELIVERY.values():
        problems.append("size")
    if fps != 24:
        problems.append("fps")
    if abs(lufs - sb["mix"]["target_lufs"]) > 1:
        problems.append("loudness")
    if tp > sb["mix"]["true_peak_db"] + 0.1:
        problems.append("true peak")
    return {"file": p.name, "seconds": secs, "size": f"{w}x{h}", "fps": fps, "lufs": lufs, "true_peak_db": tp,
            "problems": problems, "sha256": cache.file_sha(p)[:16]}
