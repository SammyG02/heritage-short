"""Narration stage: one WAV per shot and language. Reads the storyboard, writes outputs/<id>/narration/.

A shot with `quote_voice` speaks its quoted words in that character's stock voice and the rest in the narrator's.
"""
import array
import io
import math
import os
import re
import wave

from . import voice_take
from .core import approvals, budget, cache, config, providers, runlog, settings
from .core.storyboard import out, require_consent, require_service

QUOTED = re.compile(r"(«[^»]*»|“[^”]*”)")
GAP_S = 0.2
ENGINES = {"gemini": None, "addis": "addis-voices-2", "omnivoice": "Lab-et/omnivoice-amharic"}
WORDS_PER_S = {"am": 1.47, "en": 2.24}  # measured on the first film
PAUSES_S = 0.6  # lead and tail added to every line when the film is edited


def engine(sb, lang):
    return sb["voices"][lang].get("engine", "gemini")


def default_engine(lang):
    """The voice service a new film starts with: the person's choice when its key is there, otherwise Google."""
    want = settings.load()["voice"]
    return "addis" if want == "addis" and lang in ("am", "en") and os.environ.get("ADDIS_API_KEY", "").strip() else "gemini"


def text_problems(sb, lang):
    """Things a voice model reads wrongly. Finding them here costs nothing; finding them by ear costs a call."""
    found = []
    for s in sb["shots"]:
        t = s["narration"][lang]
        tests = [(r"[0-9%]", "write numbers and % as words"), (r"[።፤፣፦?!,;:]\s*[።፤፣]", "two punctuation marks together"), (r"\s{2,}|^\s|\s$", "extra spaces")]
        if lang == "am":
            tests.append((r"[A-Za-z]", "Latin letters in an Amharic line"))
        found += [f"{s['id']}: {why}" for pattern, why in tests if re.search(pattern, t)]
        if t.count("«") != t.count("»") or t.count("“") != t.count("”"):
            found.append(f"{s['id']}: a quote mark is missing")
        if s.get("quote_voice") and not QUOTED.search(t):
            found.append(f"{s['id']}: quote_voice is set but nothing is in quote marks")
    return found


def estimate_s(sb, lang):
    """Film length: measured for lines that have a voice, estimated from word counts for the rest."""
    total = sb["end_card"]["duration_s"]
    for s in sb["shots"]:
        p = path(sb, s, lang)
        if cache.fresh(p, inputs(sb, s, lang)):
            a, b = speech(p)
            voice = b - a
        else:
            voice = len(s["narration"][lang].split()) / WORDS_PER_S.get(lang, 2.0)
        total += max(s["duration_s"] if voice + PAUSES_S < s["duration_s"] else 0, voice + PAUSES_S)
    return total


def folder(sb, lang):
    """Each service keeps its own files, so switching service never loses a voice already made."""
    eng = engine(sb, lang)
    return out(sb, "narration", lang, *([] if eng == "gemini" else [eng]))


def heard_before(sb, lang):
    """One recording of this film for each Google voice it has used, the shortest, so a voice can be heard again for free."""
    base, found = out(sb, "narration", lang), {}
    for meta in [*base.glob("*.wav.meta.json"), *(base / "parts").glob("*.wav.meta.json")]:
        wav = meta.with_name(meta.name[:-len(".meta.json")])
        voice = cache.read_meta(wav).get("inputs", {}).get("voice")
        if voice and wav.exists() and (voice not in found or wav.stat().st_size < found[voice].stat().st_size):
            found[voice] = wav
    return found


def path(sb, shot, lang):
    return folder(sb, lang) / f"{shot['id']}.wav"


def part_path(sb, shot, lang, i):
    return folder(sb, lang) / "parts" / f"{shot['id']}_{i}.wav"


def parts(sb, shot, lang):
    """One set of TTS inputs per speaker turn."""
    v = sb["voices"][lang]
    model, text, who = shot.get("tts_model") or v.get("model", sb["models"]["tts"]), shot["narration"][lang], shot.get("quote_voice")
    if engine(sb, lang) != "gemini":
        model = ENGINES[engine(sb, lang)]
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


def approval_key(sb, shot, lang):
    """The exact recording a person heard: what was asked for and the sound itself. None when there is no current recording."""
    p, inp = path(sb, shot, lang), inputs(sb, shot, lang)
    return f"{cache.key(inp)}:{cache.file_sha(p)}" if cache.fresh(p, inp) else None


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


def _order(sb, first, turns):
    """One model for the whole job when any has room for it, so the voice does not change halfway."""
    models = list(dict.fromkeys([first, *sb["models"].get("tts_fallbacks", [])]))
    return sorted(models, key=lambda m: budget.tts_left(m) < turns)


def _speak(sb, item, inp, turns=1):
    """One line. Returns (wav, model used). The same stock voice name is kept when a fallback model has to step in."""
    require_consent(sb)
    lang = item.split("/")[0]
    require_service(sb, {"gemini": "google", "addis": "addis", "omnivoice": "kaggle"}[engine(sb, lang)])
    if engine(sb, lang) == "addis":
        addis_consent(sb, lang)
        return providers.addis_tts("narration", item, inp["text"], inp["voice"], lang), inp["model"]
    error = None
    for model in _order(sb, inp["model"], turns):
        if not budget.tts_left(model):
            error = error or providers.ProviderError(f"{model} has no free calls left until {budget.local(budget.tts_reset())}")
            continue
        try:
            return providers.gemini_tts("narration", item, inp["text"], inp["voice"], inp["style"], model), model
        except providers.ProviderError as e:
            error = error or e
            print(f"    {model} unavailable for {item}")
    raise error


def take(sb, lang, todo):
    """All the given shots in one call, cut into one WAV each. Returns {shot id: (wav, model)} or raises."""
    who = {"narrator": sb["voices"][lang], **sb["voices"][lang].get("characters", {})}
    turns, names = [], []
    for s in todo:
        pieces = parts(sb, s, lang)
        for i, part in enumerate(pieces):
            speaker = next(n for n, v in who.items() if v["voice"] == part["voice"])
            names.append(speaker)
            turns.append({"speaker": speaker.title(), "text": part["text"], "style": part["style"], "pause": i == len(pieces) - 1})
    voices = {n.title(): {"voice": v["voice"], "style": v["style"]} for n, v in who.items() if n in names}
    first, error = parts(sb, todo[0], lang)[0]["model"], None
    for model in _order(sb, first, 1):
        if not budget.tts_left(model):
            continue
        try:
            wav = providers.gemini_take("narration", f"{lang}/{todo[0]['id']}-{todo[-1]['id']}", turns, voices, model)
        except providers.ProviderError as e:
            error = e
            print(f"    {model} unavailable: {str(e)[:120]}")
            continue
        takes = out(sb, "narration", lang, "takes")
        takes.mkdir(parents=True, exist_ok=True)
        kept = takes / f"{todo[0]['id']}-{todo[-1]['id']}_{cache.key({'t': turns, 'v': voices, 'm': model})[:8]}_{len(list(takes.glob('*.wav'))) + 1}.wav"
        kept.write_bytes(wav)  # paid for: keep it even if it cannot be cut
        pieces = voice_take.split(wav, [s["narration"][lang] for s in todo])
        return {s["id"]: (w, model) for s, w in zip(todo, pieces)}
    raise error or providers.ProviderError(f"No free voice calls left until {budget.local(budget.tts_reset())}")


def one_call(sb, lang, todo):
    return engine(sb, lang) == "gemini" and len(todo) > 1 and len({p["voice"] for s in todo for p in parts(sb, s, lang)}) <= 2 and not any(s.get("tts_model") for s in todo)


def calls_needed(sb, lang, todo):
    """Fewest calls this job can take."""
    if engine(sb, lang) != "gemini" or not todo:
        return 0
    together = [s for s in todo if not s.get("tts_model")]
    alone = [s for s in todo if s.get("tts_model")]
    count = lambda xs: sum(len(parts(sb, s, lang)) for s in xs)  # noqa: E731
    return (1 if one_call(sb, lang, together) else count(together)) + count(alone)


def addis_consent(sb, lang):
    """Addis AI may train on what it is sent, so a true story needs a yes to that as well."""
    if engine(sb, lang) == "addis" and sb["people"].get("based_on_real_people") and not sb["people"].get("addis_consent"):
        raise config.PipelineError("This is a true story and Addis AI may train on it. Record that the people in it agreed: Services, Addis AI.")


def check_ready(sb, lang, todo):
    """Everything that can be wrong without hearing it, checked before a call is spent."""
    require_consent(sb)
    require_service(sb, {"gemini": "google", "addis": "addis", "omnivoice": "kaggle"}[engine(sb, lang)])
    addis_consent(sb, lang)
    ids = {s["id"] for s in todo}
    if bad := [x for x in text_problems(sb, lang) if x.split(":")[0] in ids]:
        raise config.PipelineError("Fix the script before making voices:\n  - " + "\n  - ".join(bad))
    for s in todo:
        approvals.need(sb, "script", s["id"], approvals.script_key(s))
    length = estimate_s(sb, lang)
    if not 55 <= length <= 94:
        raise config.PipelineError(f"The script would make a film of about {length:.0f} s; it must be 60-90 s. Change the script first.")


def stale(sb, lang, only=None, force=False):
    return [s for s in sb["shots"] if (not only or s["id"] in only) and (force or not cache.fresh(path(sb, s, lang), inputs(sb, s, lang)))]


def run(sb, lang, force=False, only=None):
    todo = stale(sb, lang, only, force)
    if todo:
        check_ready(sb, lang, todo)
        if engine(sb, lang) == "omnivoice":
            raise config.PipelineError("OmniVoice runs on the Kaggle GPU: use gpu submit voice, then gpu fetch voice.")
    made = {}
    if todo and engine(sb, lang) == "gemini":
        models = list(dict.fromkeys([parts(sb, s, lang)[0]["model"] for s in todo] + sb["models"].get("tts_fallbacks", [])))
        free, least = sum(budget.tts_left(m) for m in models), calls_needed(sb, lang, todo)
        print(f"  voice: {len(todo)} lines, {least} call{'s' * (least != 1)} if all goes well, about {free} free today")
        if free < least:
            raise config.PipelineError(f"Not enough free voice calls: {least} needed, {free} left until {budget.local(budget.tts_reset())}. "
                                       "Nothing was made. Wait, or choose another voice service.")
        together = [s for s in todo if not s.get("tts_model")]  # a line pinned to a model is made on its own
        runlog.step(f"Google is reading {len(together)} lines in one recording, then the studio cuts it into lines")
        if one_call(sb, lang, together):
            half = (len(together) + 1) // 2
            for group in ([together], [together[:half], together[half:]] if len(together) > 3 else []):
                try:
                    for g in group:
                        if g and not all(s["id"] in made for s in g):
                            made.update(take(sb, lang, g) if len(g) > 1 else {})
                except providers.ProviderError as e:
                    print(f"  one call failed: {str(e)[:160]}")
                    break
                except config.PipelineError as e:
                    print(f"  could not cut the recording safely: {e}")
                if len(made) == len(together):
                    break
            rest = [s for s in todo if s["id"] not in made]
            turns = sum(len(parts(sb, s, lang)) for s in rest)
            free = sum(budget.tts_left(m) for m in models)
            if rest and free < turns:
                _store(sb, lang, todo, made)
                raise config.PipelineError(f"{len(made)} lines are ready. {len(rest)} could not be cut from one recording and need {turns} calls, {free} left until "
                                           f"{budget.local(budget.tts_reset())}. The recordings are kept in narration/{lang}/takes.")
    _store(sb, lang, todo, made)
    rest = [s for s in todo if s["id"] not in made]
    left_turns = sum(len(parts(sb, s, lang)) for s in rest)
    for k, shot in enumerate(rest, 1):
        p, inp = path(sb, shot, lang), inputs(sb, shot, lang)
        turns = parts(sb, shot, lang)
        runlog.progress(k, len(rest), f"line {sb['shots'].index(shot) + 1}")
        runlog.step(f"{ {'gemini': 'Google', 'addis': 'Addis AI', 'omnivoice': 'OmniVoice'}.get(engine(sb, lang), 'The voice service')} is reading the line")
        if len(turns) == 1:
            data, used = _speak(sb, f"{lang}/{shot['id']}", inp, left_turns)
            left_turns -= 1
            cache.store(p, data, inp, model_used=used)
        else:
            files = []
            for i, turn in enumerate(turns, 1):
                f = part_path(sb, shot, lang, i)
                if force or not cache.fresh(f, turn):
                    data, used = _speak(sb, f"{lang}/{shot['id']}_{i}", turn, left_turns)
                    cache.store(f, data, turn, model_used=used)
                left_turns -= 1
                files.append(f)
            cache.store(p, join(files), inp)
        print(f"  narration {lang}/{shot['id']}  {seconds(p):.1f}s")
    print(f"  narration {lang}: {len(todo)} generated, {(len(only) if only else len(sb['shots'])) - len(todo)} cached")


def _store(sb, lang, todo, made):
    for s in todo:
        if s["id"] in made:
            wav, model = made[s["id"]]
            cache.store(path(sb, s, lang), wav, inputs(sb, s, lang), model_used=model, one_call=True)
            print(f"  narration {lang}/{s['id']}  {seconds(path(sb, s, lang)):.1f}s  (one call)")
