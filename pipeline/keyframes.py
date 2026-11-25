"""Keyframe stage: reference sheet first, then one image per shot and aspect ratio."""
from . import qa
from .core import cache, providers
from .core.storyboard import out, require_consent

# Multiples of 16, close to the delivery ratios.
SIZES = {"9x16": (768, 1344), "16x9": (1344, 768)}
FRAMING = {"9x16": "tall vertical scene, subject large in the middle third, the painted scene continues down to the bottom edge",
           "16x9": "horizontal composition, subject in the centre, calm empty space near the bottom"}


def ref_path(sb, name, seed):
    return out(sb, "references", f"{name}_{seed}.png")


def ref_inputs(sb, name, seed):
    ref = sb["references"][name]
    inp = {"stage": "reference/1", "model": sb["models"]["image"], "seed": seed, "size": [1024, 1024],
           "prompt": f"{ref['prompt']}. {sb['style_block']}"}
    if ref.get("from"):
        p = ref_path(sb, ref["from"], sb["references"][ref["from"]]["chosen_seed"])
        inp["references"] = [cache.file_sha(p) if p.exists() else "missing"]
    return inp


def path(sb, shot, ratio):
    return out(sb, "keyframes", f"{shot['id']}_{ratio}.png")


def prompt(sb, shot, ratio):
    """The same locked description of each character goes into every shot that shows them."""
    looks = [f"Reference image {i} is the {n.replace('_', ' ')}: {sb['references'][n]['look']}. Same face, hair and clothes as reference image {i}"
             for i, n in enumerate(shot["references"], 1) if sb["references"][n].get("look")]
    bits = [f"{shot['size']} shot", shot["image_prompt"], *([f"Visible emotion: {shot['emotion']}"] if shot.get("emotion") else []),
            *looks, FRAMING[ratio], sb["style_block"]]
    return ". ".join(bits)


def inputs(sb, shot, ratio):
    refs = [ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in shot["references"]]
    return {"stage": "keyframe/1", "model": sb["models"]["image"], "seed": shot["seed"], "size": list(SIZES[ratio]),
            "prompt": prompt(sb, shot, ratio),
            # A missing reference never matches a cached key, so it is generated first.
            "references": [cache.file_sha(r) if r.exists() else "missing" for r in refs]}


def run_references(sb, force=False):
    made = 0
    for name, ref in sorted(sb["references"].items(), key=lambda kv: bool(kv[1].get("from"))):  # parents first
        for seed in ref["seeds"]:
            p, inp = ref_path(sb, name, seed), ref_inputs(sb, name, seed)
            if not force and cache.fresh(p, inp):
                continue
            require_consent(sb)
            base = [ref_path(sb, ref["from"], sb["references"][ref["from"]]["chosen_seed"])] if ref.get("from") else []
            data = providers.flux("references", f"{name}_{seed}", inp["prompt"], *inp["size"], seed, inp["model"], base)
            cache.store(p, data, inp)
            made += 1
    print(f"  references: {made} generated")


def run(sb, ratios=tuple(SIZES), force=False):
    made = 0
    for shot in sb["shots"]:
        for ratio in ratios:
            p, inp = path(sb, shot, ratio), inputs(sb, shot, ratio)
            if not force and cache.fresh(p, inp):
                continue
            refs = [ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in shot["references"]]
            require_consent(sb)
            data, report = qa.best_of(sb, shot, ratio, inp, refs)
            cache.store(p, data, inp, qa=report)
            made += 1
            print(f"  keyframe {shot['id']}_{ratio}")
    print(f"  keyframes: {made} generated, {len(sb['shots']) * len(ratios) - made} cached")
