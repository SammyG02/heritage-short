"""Music stage: the chosen ACE-Step candidate, or a synthesised placeholder until one exists."""
import io
import math
import random
import struct
import wave

from .core import cache
from .core.storyboard import out

RATE = 24000


def path(sb, seed):
    return out(sb, "music", f"score_{seed}.wav")


def inputs(sb, seed):
    m = sb["music"]
    return {"stage": "music/1", "model": sb["models"]["music"], "caption": m["caption"], "bpm": m["bpm"],
            "key": m["key"], "duration_s": m["duration_s"], "seed": seed}


def placeholder_path(sb):
    return out(sb, "music", "placeholder.wav")


def _placeholder(sb) -> bytes:
    """Sparse plucked pentatonic notes over a quiet drone. Deterministic, no model involved."""
    rng = random.Random(7)
    n = int(sb["music"]["duration_s"] * RATE)
    buf = [0.05 * math.sin(2 * math.pi * 73.42 * i / RATE) for i in range(n)]
    scale = [146.83, 174.61, 196.0, 220.0, 261.63, 293.66]
    beat = 60 / sb["music"]["bpm"]
    t = 0.2
    while t < sb["music"]["duration_s"] - 3:
        # Karplus-Strong: a decaying noise burst that sounds like a plucked string.
        period = int(RATE / rng.choice(scale))
        ring = [rng.uniform(-1, 1) for _ in range(period)]
        start = int(t * RATE)
        for i in range(min(int(2.5 * RATE), n - start)):
            k = i % period
            buf[start + i] += 0.16 * ring[k]
            ring[k] = 0.4985 * (ring[k] + ring[(k + 1) % period])
        t += beat * rng.choice([1, 2, 2, 3])
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, x)) * 32000)) for x in buf))
    return raw.getvalue()


def placeholder(sb):
    p = placeholder_path(sb)
    inp = {"stage": "placeholder/1", "bpm": sb["music"]["bpm"], "duration_s": sb["music"]["duration_s"]}
    if not cache.fresh(p, inp):
        cache.store(p, _placeholder(sb), inp)
        print("  placeholder music made in code")
    return p


def score(sb):
    """Return (path, kind)."""
    seed = sb["music"]["chosen_seed"]
    p = path(sb, seed)
    if cache.fresh(p, inputs(sb, seed)):
        return p, "ace-step"
    print("  music: no matching ACE-Step score yet, using the placeholder")
    return placeholder(sb), "placeholder"
