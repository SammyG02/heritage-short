"""One voice call for a whole script, cut back into one file per shot.

The free limit counts calls, not words. The cuts are the longest pauses, and only when they are clearly
longer than every other pause and each piece is about as long as its text. Otherwise the recording is kept and the cut is refused.
"""
import array
import io
import wave

from .core import config

FRAME_S = 0.02
MIN_GAP_S = 0.28
MIN_BETWEEN_S = 0.6
CLEAR = 1.2
RATIO = (0.45, 2.2)  # a piece may be this much shorter or longer than its text suggests


def read(wav: bytes):
    with wave.open(io.BytesIO(wav)) as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise config.PipelineError("The recording must be 16-bit mono.")
        return array.array("h", w.readframes(w.getnframes())), w.getframerate()


def write(samples, rate) -> bytes:
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return raw.getvalue()


def silences(samples, rate):
    """[(start, end)] in seconds of every quiet stretch between words, longest pauses included."""
    step = max(1, int(rate * FRAME_S))
    peaks = [max(map(abs, samples[i:i + step])) for i in range(0, len(samples), step)]
    loud = sorted(peaks)[int(len(peaks) * 0.95)] if peaks else 0
    quiet_below = max(120, loud * 0.04)
    found, start = [], None
    for i, p in enumerate([*peaks, 10 ** 9]):
        if p < quiet_below and start is None:
            start = i
        elif p >= quiet_below and start is not None:
            if (i - start) * FRAME_S >= MIN_GAP_S:
                found.append((start * step / rate, i * step / rate))
            start = None
    return found


def split(wav: bytes, texts: list[str]) -> list[bytes]:
    """Cut the recording into len(texts) pieces, or raise PipelineError when no safe cut exists."""
    samples, rate = read(wav)
    total = len(samples) / rate
    gaps = silences(samples, rate)
    first = next((e for s, e in gaps if s < 0.01), 0.0)
    last = next((s for s, e in gaps if e > total - 0.05), total)
    inner = [g for g in gaps if g[0] > first and g[1] < last]
    n = len(texts)
    if n == 1:
        return [wav]
    if len(inner) < n - 1:
        raise config.PipelineError(f"Found {len(inner)} pauses, need {n - 1}.")
    by_length = sorted(inner, key=lambda g: g[0] - g[1])
    chosen, rest = sorted(by_length[:n - 1]), by_length[n - 1:]
    shortest = min(e - s for s, e in chosen)
    longest_inside = max((e - s for s, e in rest), default=0.0)
    # The pause between lines must be clearly longer than any pause inside a line. Guessing here cuts lines in the wrong place.
    if shortest < MIN_BETWEEN_S or shortest < CLEAR * longest_inside:
        raise config.PipelineError(f"The pauses between lines ({shortest:.1f} s) are not clearly longer than those inside lines ({longest_inside:.1f} s).")
    edges = [first, *(x for s, e in chosen for x in (s, e)), last]
    cuts = list(zip(edges[::2], edges[1::2]))
    size = [sum(ch.isalnum() for ch in x) + 4 for x in texts]
    speech = sum(e - s for s, e in cuts)
    want = [speech * x / sum(size) for x in size]
    for k, (s, e) in enumerate(cuts):
        if not RATIO[0] <= (e - s) / want[k] <= RATIO[1]:
            raise config.PipelineError(f"Line {k + 1} came out {e - s:.1f} s, about {want[k]:.1f} s was expected.")
    pad = 0.1
    return [write(samples[int(max(0, s - pad) * rate):int(min(total, e + pad) * rate)], rate) for s, e in cuts]
