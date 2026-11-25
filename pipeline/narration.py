"""Narration stage: one WAV per shot and language. Reads the storyboard, writes outputs/<id>/narration/.

A shot with `quote_voice` speaks its quoted words in that character's stock voice and the rest in the narrator's.
"""
import array
import io
import math
import re
import wave

from .core import cache, config, providers
from .core.storyboard import out, require_consent

QUOTED = re.compile(r"(«[^»]*»|“[^”]*”)")
GAP_S = 0.2


def path(sb, shot, lang):
    return out(sb, "narration", lang, f"{shot['id']}.wav")


def part_path(sb, shot, lang, i):
    return out(sb, "narration", lang, "parts", f"{shot['id']}_{i}.wav")


def parts(sb, shot, lang):
    """One set of TTS inputs per speaker turn."""
    v = sb["voices"][lang]
    model, text, who = shot.get("tts_model") or v.get("model", sb["models"]["tts"]), shot["narration"][lang], shot.get("quote_voice")
    feel = f", {shot['voice_emotion']}" if shot.get("voice_emotion") else ""
    if not who:
        return [{"stage": "narration/1", "model": model, "text": text, "voice": v["voice"], "style": v["style"] + feel}]
    rows = []
    for piece in QUOTED.split(text):
        speaker = v["characters"][who] if QUOTED.fullmatch(piece) else v
        words = piece.strip(" «»“”")
        if re.search(r"\w", words):
            rows.append({"stage": "narration/1", "model": model, "text": words, "voice": speaker["voice"], "style": speaker["style"] + feel})
    return rows


def inputs(sb, shot, lang):
    p = parts(sb, shot, lang)
    return p[0] if len(p) == 1 else {"stage": "narration/2", "gap_s": GAP_S, "parts": p}


def seconds(p) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def speech(p):
    """(start, end) in seconds of the spoken part, so silent edges do not lengthen the film."""
    with wave.open(str(p)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            return 0.0, w.getnframes() / w.getframerate()
        rate, data = w.getframerate(), array.array("h", w.readframes(w.getnframes()))
    step = rate // 50
    loud = [i for i in range(0, len(data), step) if max(map(abs, data[i:i + step])) > 250]
    if not loud:
        return 0.0, len(data) / rate
    return max(0.0, loud[0] / rate - 0.06), min(len(data) / rate, (loud[-1] + step) / rate + 0.12)


def join(files) -> bytes:
    """Put speaker turns one after another at the same average level."""
    turns, rate = [], None
    for f in files:
        with wave.open(str(f)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1 or rate not in (None, w.getframerate()):
                raise config.PipelineError(f"{f.name}: voices must all be 16-bit mono at one sample rate")
            rate = w.getframerate()
            turns.append(array.array("h", w.readframes(w.getnframes())))
    rms = [math.sqrt(sum(x * x for x in t) / max(len(t), 1)) or 1.0 for t in turns]
    joined = array.array("h")
    for i, t in enumerate(turns):
        gain = min(rms[0] / rms[i], 32000 / max(max(map(abs, t), default=1), 1))
        if i:
            joined.extend([0] * int(GAP_S * rate))
        joined.extend(int(x * gain) for x in t)
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(joined.tobytes())
    return raw.getvalue()


def _speak(sb, item, inp):
    """Returns (wav, model used). The same stock voice name is kept when a fallback model has to step in."""
    require_consent(sb)
    error = None
    for model in dict.fromkeys([inp["model"], *sb["models"].get("tts_fallbacks", [])]):
        try:
            return providers.gemini_tts("narration", item, inp["text"], inp["voice"], inp["style"], model), model
        except providers.ProviderError as e:
            error = error or e
            print(f"    {model} unavailable for {item}")
    raise error


def run(sb, lang, force=False):
    made = 0
    for shot in sb["shots"]:
        p, inp = path(sb, shot, lang), inputs(sb, shot, lang)
        if not force and cache.fresh(p, inp):
            continue
        turns = parts(sb, shot, lang)
        if len(turns) == 1:
            data, used = _speak(sb, f"{lang}/{shot['id']}", inp)
            cache.store(p, data, inp, model_used=used)
        else:
            files = []
            for i, turn in enumerate(turns, 1):
                f = part_path(sb, shot, lang, i)
                if force or not cache.fresh(f, turn):
                    data, used = _speak(sb, f"{lang}/{shot['id']}_{i}", turn)
                    cache.store(f, data, turn, model_used=used)
                files.append(f)
            cache.store(p, join(files), inp)
        made += 1
        print(f"  narration {lang}/{shot['id']}  {seconds(p):.1f}s")
    print(f"  narration {lang}: {made} generated, {len(sb['shots']) - made} cached")
