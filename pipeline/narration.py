"""Narration stage: one WAV per shot and language. Reads the storyboard, writes outputs/<id>/narration/."""
import wave

from .core import cache, providers
from .core.storyboard import out


def path(sb, shot, lang):
    return out(sb, "narration", lang, f"{shot['id']}.wav")


def inputs(sb, shot, lang):
    v = sb["voices"][lang]
    return {"stage": "narration/1", "model": v.get("model", sb["models"]["tts"]), "text": shot["narration"][lang],
            "voice": v["voice"], "style": v["style"]}


def seconds(p) -> float:
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


def run(sb, lang, force=False):
    made = 0
    for shot in sb["shots"]:
        p, inp = path(sb, shot, lang), inputs(sb, shot, lang)
        if not force and cache.fresh(p, inp):
            continue
        data = providers.gemini_tts("narration", f"{lang}/{shot['id']}", inp["text"], inp["voice"], inp["style"], inp["model"])
        cache.store(p, data, inp)
        made += 1
        print(f"  narration {lang}/{shot['id']}  {seconds(p):.1f}s")
    print(f"  narration {lang}: {made} generated, {len(sb['shots']) - made} cached")
