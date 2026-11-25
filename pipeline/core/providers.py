"""Hosted model calls, with retries. Every attempt is logged."""
import base64
import io
import json
import random
import re
import tempfile
import time
import wave
from pathlib import Path

import requests
from PIL import Image

from . import config, runlog

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
MAX_ATTEMPTS = 3
# USD list prices read on 25 Nov 2026; used for the list-price equivalent only.
PRICE_TEXT = (0.75, 3.75)          # Gemini 3.8 Flash, per million tokens in / out
PRICE_TTS = (0.50, 9.00)           # Gemini 3.8 Flash TTS
PRICE_FLUX = (0.000059, 0.000287)  # klein 4B, per 512 px tile in / out


class ProviderError(config.PipelineError):
    def __init__(self, message, retryable=False, wait=None):
        super().__init__(message)
        self.retryable, self.wait = retryable, wait


def _check(r):
    if r.ok:
        return r
    daily = r.status_code == 429 and re.search(r"per ?day|daily", r.text, re.I)
    m = re.search(r"retry in ([\d.]+)s", r.text) or re.search(r'"retryDelay":\s*"([\d.]+)s"', r.text)
    raise ProviderError(f"HTTP {r.status_code}: {r.text[:500]}",
                        retryable=(r.status_code == 429 or r.status_code >= 500) and not daily,
                        wait=float(m.group(1)) + 1 if m else None)


def retry(fn):
    """Call fn(attempt) up to MAX_ATTEMPTS times with exponential backoff and jitter."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn(attempt)
        except (ProviderError, requests.RequestException) as e:
            retryable = getattr(e, "retryable", isinstance(e, (requests.Timeout, requests.ConnectionError)))
            if not retryable or attempt == MAX_ATTEMPTS:
                raise e if isinstance(e, ProviderError) else ProviderError(str(e))
            wait = min(getattr(e, "wait", None) or 4 * 2 ** (attempt - 1), 70) + random.random()
            print(f"    attempt {attempt} failed, retrying in {wait:.0f}s: {runlog.redact(str(e))[:110]}")
            time.sleep(wait)


def _headers():
    return {"x-goog-api-key": config.secret("GEMINI_API_KEY")}


def _price(n_in, n_out, rate):
    return round((n_in * rate[0] + n_out * rate[1]) / 1e6, 6)


def _small_jpeg(data):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((768, 768))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def gemini_json(stage, item, prompt, model, seed=None, temperature=0.8, images=()):
    parts = [{"inlineData": {"mimeType": "image/jpeg", "data": _small_jpeg(d)}} for d in images] + [{"text": prompt}]
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature}}
    if seed is not None:
        body["generationConfig"]["seed"] = seed

    def go(attempt):
        with runlog.call(stage, item, "gemini", model, {"prompt": prompt, "temperature": temperature}, seed, attempt) as rec:
            r = _check(requests.post(f"{GEMINI}/models/{model}:generateContent", headers=_headers(),
                                     json=body, timeout=180)).json()
            u = r.get("usageMetadata", {})
            n_in = u.get("promptTokenCount", 0)
            n_out = u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0)
            rec["usage"] = {"in": n_in, "out": n_out}
            rec["list_price_usd"] = _price(n_in, n_out, PRICE_TEXT)
            try:
                return json.loads("".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"]))
            except (KeyError, IndexError, ValueError) as e:
                raise ProviderError(f"Model did not return usable JSON: {e}", retryable=True)
    return retry(go)


def _tts_generate_content(text, voice, style, model, speech=None):
    """Older TTS models: generateContent, raw 16-bit PCM. Returns (wav bytes, tokens in, tokens out)."""
    body = {"contents": [{"parts": [{"text": text if speech else f"Read aloud, {style}:\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": speech or {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    r = _check(requests.post(f"{GEMINI}/models/{model}:generateContent", headers=_headers(), json=body, timeout=180)).json()
    found = [p["inlineData"] for c in r.get("candidates", []) for p in c.get("content", {}).get("parts", []) if "inlineData" in p]
    if not found:
        raise ProviderError("TTS returned no audio", retryable=True)
    rate = re.search(r"rate=(\d+)", found[0].get("mimeType", ""))
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate.group(1)) if rate else 24000)
        w.writeframes(b"".join(base64.b64decode(f["data"]) for f in found))
    u = r.get("usageMetadata", {})
    return raw.getvalue(), u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)


def gemini_tts(stage, item, text, voice, style, model) -> bytes:
    """Return a WAV file. 3.8 TTS uses the Interactions API, not generateContent."""
    body = {"model": model,
            "input": [{"type": "user_input", "content": [{"type": "text", "text": text,
                       "annotations": [{"type": "speech_metadata", "style": style}]}]}],
            "response_format": {"type": "audio"},
            "generation_config": {"speech_config": [{"voice": voice}]}}

    def go(attempt):
        with runlog.call(stage, item, "gemini", model, {"text": text, "voice": voice, "style": style}, None, attempt) as rec:
            if "3.8" not in model:
                data, n_in, n_out = _tts_generate_content(text, voice, style, model)
                rec["usage"] = {"in": n_in, "out": n_out}  # no list price recorded: not checked for this model
                rec["output"] = {"bytes": len(data)}
                return data
            r = _check(requests.post(f"{GEMINI}/interactions", headers=_headers(), json=body, timeout=180)).json()
            audio = [c for s in r.get("steps", []) if s.get("type") == "model_output"
                     for c in s.get("content", []) if c.get("type") == "audio"]
            if not audio:
                raise ProviderError("TTS returned no audio", retryable=True)
            u = r.get("usage", {})
            n_in, n_out = u.get("total_input_tokens", 0), u.get("total_output_tokens", 0)
            rec["usage"] = {"in": n_in, "out": n_out}
            rec["list_price_usd"] = _price(n_in, n_out, PRICE_TTS)
            data = base64.b64decode(audio[-1]["data"])
            rec["output"] = {"bytes": len(data)}
            return data
    return retry(go)


def gemini_take(stage, item, turns, voices, model) -> bytes:
    """Several lines, one or two speakers, in one call. turns: [{"speaker", "text"}], voices: {speaker: {"voice", "style"}}."""
    names = list(dict.fromkeys(t["speaker"] for t in turns))
    if len(names) > 2:
        raise ProviderError("One call can hold two speakers")
    # A blank line marks the end of a shot; speakers inside one shot follow each other directly.
    text = "".join((f"{t['speaker']}: {t['text']}" if len(names) > 1 else t["text"]) + ("\n\n" if t.get("pause") else "\n") for t in turns).strip()
    style = lambda t: t.get("style") or voices[t["speaker"]]["style"]  # noqa: E731

    def go(attempt):
        with runlog.call(stage, item, "gemini", model, {"lines": len(turns), "text": text, "styles": [style(t) for t in turns], "voices": {n: voices[n] for n in names}}, None, attempt) as rec:
            if "3.8" in model:
                content = [{"type": "text", "text": t["text"] + (" <long pause>" if t.get("pause") else ""),
                            "annotations": [{"type": "speech_metadata", "style": style(t),
                                             **({"speaker": t["speaker"]} if len(names) > 1 else {})}]} for t in turns]
                speech = ({"speakers": [{"speaker": n, "voice": voices[n]["voice"]} for n in names]} if len(names) > 1
                          else [{"voice": voices[names[0]]["voice"]}])
                r = _check(requests.post(f"{GEMINI}/interactions", headers=_headers(), timeout=300, json={
                    "model": model, "input": [{"type": "user_input", "content": content}], "response_format": {"type": "audio"},
                    "generation_config": {"speech_config": speech}})).json()
                audio = [c["data"] for s in r.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
                if not audio:
                    raise ProviderError("TTS returned no audio", retryable=True)
                data = base64.b64decode(audio[-1])
                u = r.get("usage", {})
                rec["usage"] = {"in": u.get("total_input_tokens", 0), "out": u.get("total_output_tokens", 0)}
            else:
                how = "; ".join(f"{n} is {voices[n]['style']}" if len(names) > 1 else voices[n]["style"] for n in names)
                felt = [f"\"{t['text'][:24]}...\": {style(t)}" for t in turns if style(t) != voices[t["speaker"]]["style"]]
                notes = " For the lines starting as follows: " + "; ".join(felt) + "." if felt else ""
                say = (f"Read only the script aloud, {how}.{notes} Leave two full seconds of silence at every blank line and no long silence anywhere else."
                       f"\n\nSCRIPT\n\n{text}")
                one = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[names[0]]["voice"]}}}
                many = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                    {"speaker": n, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[n]["voice"]}}} for n in names]}}
                data, n_in, n_out = _tts_generate_content(say, None, None, model, many if len(names) > 1 else one)
                rec["usage"] = {"in": n_in, "out": n_out}
            rec["output"] = {"bytes": len(data)}
            return data
    return retry(go)


ADDIS = "https://api.addisassistant.com/api/v1/voice"


def _addis_headers():
    return {"x-api-key": config.secret("ADDIS_API_KEY"), "Content-Type": "application/json"}


def addis_voices(language):
    r = _check(requests.get(f"{ADDIS}/voices", params={"language": language}, headers=_addis_headers(), timeout=30)).json()
    rows = r.get("data", r)
    rows = rows.get("voices", rows.get("items", [])) if isinstance(rows, dict) else rows
    return [{"id": str(v.get("voice_id") or v.get("id")), "name": str(v.get("name") or v.get("voice_id") or v.get("id")), "gender": str(v.get("gender") or "")}
            for v in rows if isinstance(v, dict)]


def addis_tts(stage, item, text, voice, language) -> bytes:
    """Addis AI Voices 2. Returns a 16-bit mono 24 kHz WAV. Uses signup credit, not a daily quota; style instructions are not supported."""
    def go(attempt):
        with runlog.call(stage, item, "addis-ai", "addis-voices-2", {"text": text, "voice": voice, "language": language}, None, attempt) as rec:
            r = _check(requests.post(f"{ADDIS}/generations", headers=_addis_headers(), timeout=180, json={
                "text": text, "voice_id": voice, "language": language, "output_format": "wav_44100"})).json()
            d = r.get("data", r)
            inline = next((d[k] for k in ("audio", "audio_data", "audio_base64") if isinstance(d.get(k), str)), None)
            if inline:
                raw = base64.b64decode(inline.split(",", 1)[-1])
            else:
                link = str(d.get("audio_url") or "")
                if not link.startswith("https://"):
                    raise ProviderError("Addis AI returned no audio")
                got = requests.get(link, timeout=120)  # a signed link: the key is not sent to it
                if not got.ok:
                    raise ProviderError(f"HTTP {got.status_code} downloading the audio", retryable=True)
                raw = got.content
            data = to_wav(raw)
            rec["output"] = {"bytes": len(data)}
            return data
    return retry(go)


def to_wav(raw: bytes) -> bytes:
    """Any audio to 16-bit mono 24 kHz, so voices from different services can be joined."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d, "in"), Path(d, "out.wav")
        src.write_bytes(raw)
        config.run_ffmpeg(["-i", src, "-ac", 1, "-ar", 24000, "-c:a", "pcm_s16le", "-bitexact", "-map_metadata", -1, dst])
        return dst.read_bytes()


def _tiles(w, h):
    return -(-w // 512) * -(-h // 512)


def flux(stage, item, prompt, width, height, seed, model, refs=()) -> bytes:
    """Return PNG bytes. refs are image paths, sent just under 512 px."""
    url = (f"https://api.cloudflare.com/client/v4/accounts/{config.secret('CLOUDFLARE_ACCOUNT_ID')}"
           f"/ai/run/{model}")
    headers = {"Authorization": "Bearer " + config.secret("CLOUDFLARE_API_TOKEN")}
    params = {"prompt": prompt, "width": width, "height": height, "references": [p.stem for p in refs]}

    def go(attempt):
        with runlog.call(stage, item, "cloudflare", model, params, seed, attempt) as rec:
            form = {"prompt": (None, prompt), "width": (None, str(width)), "height": (None, str(height)),
                    "seed": (None, str(seed))}
            for i, p in enumerate(refs):
                im = Image.open(p).convert("RGB")
                im.thumbnail((511, 511))
                buf = io.BytesIO()
                im.save(buf, "PNG")
                form[f"input_image_{i}"] = (f"ref{i}.png", buf.getvalue(), "image/png")
            r = _check(requests.post(url, headers=headers, files=form, timeout=180)).json()
            b64 = (r.get("result") or {}).get("image") or r.get("image")
            if not b64:
                raise ProviderError("No image in response: " + str(r)[:200], retryable=True)
            rec["list_price_usd"] = round(len(refs) * PRICE_FLUX[0] + _tiles(width, height) * PRICE_FLUX[1], 6)
            im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "PNG")
            rec["output"] = {"width": im.width, "height": im.height, "bytes": buf.tell()}
            return buf.getvalue()
    return retry(go)
