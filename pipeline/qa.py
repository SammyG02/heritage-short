"""Picture check: a vision model compares each keyframe with the reference sheet and the shot's intent.

A failing picture is drawn again with another seed, up to MAX_TRIES and EXTRA_PER_RUN, and the best one is kept. If no vision model is
available the picture is kept and marked unchecked, so a quota never stops a film but also never hides.
"""
from . import keyframes
from .core import budget, config, providers, settings

MAX_TRIES = 2
EXTRA_PER_RUN = 6  # redraws allowed in one run, whatever the checker thinks
PASS = 7
SEED_STEP = 101
MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]
GROQ_SEES, GROQ_IMAGES = "qwen/qwen3.8-27b", 3  # Groq's vision page, 26 Nov 2026
PROMPT = """You check one frame of an animated film before it is used. The first {n} image(s) are the approved character references, in this order: {names}.
The last image is the new frame. It should show: {shot}
Expected emotion: {emotion}
Expected style: {style}
Score 0-10 each, strictly. Use 10 for identity when there are no references, and 10 for emotion when no face is expected.
Return JSON: {{"identity": same face, hair and clothes as the references, "emotion": visible emotion matches, "content": shows what was asked with the right number of people and objects,
"anatomy": hands, faces and bodies are whole and natural, "style": matches the style and has no writing or signature, "problem": one short sentence naming the worst fault or "none"}}"""
KEYS = ("identity", "emotion", "content", "anatomy", "style")


def check(sb, shot, ratio, png, refs):
    """Return scores, or None when no vision model answers."""
    text = PROMPT.format(n=len(refs), names=", ".join(shot["references"]) or "no references", shot=shot["image_prompt"],
                         emotion=shot.get("emotion", "not specified"), style=sb["style_block"])
    choice = settings.load()["writer"]
    images = [p.read_bytes() for p in refs] + [png]
    if choice.startswith("groq:") and (choice != "groq:" + GROQ_SEES or len(images) > GROQ_IMAGES):
        return None
    for one in ([choice] if choice != "auto" else ["gemini:" + m for m in MODELS]):
        try:
            r, model = providers.write_json("qa", f"{shot['id']}_{ratio}", text, one, MODELS, temperature=0, images=images)
            scores = {k: float(r[k]) for k in KEYS}
            return {**scores, "worst": min(scores.values()), "problem": str(r.get("problem", ""))[:200], "model": model}
        except (config.PipelineError, KeyError, TypeError, ValueError) as e:
            print(f"    check by {one} unavailable: {type(e).__name__}")
    return None


def best_of(sb, shot, ratio, inp, refs, extra=None):
    """Draw, check, redraw. Returns (png, report)."""
    best, tries, extra = None, [], extra if extra is not None else [MAX_TRIES]
    for i in range(MAX_TRIES):
        if i:
            if not extra[0] or budget.flux_left() < keyframes.cost(sb, shot, ratio):
                break
            extra[0] -= 1
        seed = inp["seed"] + i * SEED_STEP
        try:
            png = providers.flux("keyframes", f"{shot['id']}_{ratio}", inp["prompt"], *inp["size"], seed, inp["model"], refs)
        except providers.ProviderError:
            if best:
                break  # out of picture quota: keep the best so far
            raise
        score = check(sb, shot, ratio, png, refs) if refs else None  # no character to compare: save the call
        tries.append({"seed": seed, "check": score})
        rank = score["worst"] if score else -1
        if best is None or rank > best[0]:
            best = (rank, png, seed)
        if score is None or rank >= PASS:
            break
        print(f"    {shot['id']}_{ratio} scored {rank:g}: {score['problem']}")
    status = "unchecked" if best[0] < 0 else "passed" if best[0] >= PASS else "below target, needs a person to look"
    return best[1], {"status": status, "seed_used": best[2], "tries": tries}
