"""Keyframe stage: reference sheet first, then one image per shot and aspect ratio."""
from .core import cache, providers
from .core.storyboard import out

# Multiples of 16, close to the delivery ratios.
SIZES = {"9x16": (768, 1344), "16x9": (1344, 768)}
FRAMING = {"9x16": "vertical composition, subject in the middle third, calm empty space near the bottom",
           "16x9": "horizontal composition, subject in the centre, calm empty space near the bottom"}


def ref_path(sb, name, seed):
    return out(sb, "references", f"{name}_{seed}.png")


def ref_inputs(sb, name, seed):
    return {"stage": "reference/1", "model": sb["models"]["image"], "seed": seed, "size": [1024, 1024],
            "prompt": f"{sb['references'][name]['prompt']}. {sb['style_block']}"}


def path(sb, shot, ratio):
    return out(sb, "keyframes", f"{shot['id']}_{ratio}.png")


def inputs(sb, shot, ratio):
    refs = [ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in shot["references"]]
    return {"stage": "keyframe/1", "model": sb["models"]["image"], "seed": shot["seed"], "size": list(SIZES[ratio]),
            "prompt": f"{shot['size']} shot. {shot['image_prompt']}. {FRAMING[ratio]}. {sb['style_block']}",
            # A missing reference never matches a cached key, so it is generated first.
            "references": [cache.file_sha(r) if r.exists() else "missing" for r in refs]}


def run_references(sb, force=False):
    made = 0
    for name, ref in sb["references"].items():
        for seed in ref["seeds"]:
            p, inp = ref_path(sb, name, seed), ref_inputs(sb, name, seed)
            if not force and cache.fresh(p, inp):
                continue
            data = providers.flux("references", f"{name}_{seed}", inp["prompt"], *inp["size"], seed, inp["model"])
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
            data = providers.flux("keyframes", f"{shot['id']}_{ratio}", inp["prompt"], *inp["size"],
                                  inp["seed"], inp["model"], refs)
            cache.store(p, data, inp)
            made += 1
            print(f"  keyframe {shot['id']}_{ratio}")
    print(f"  keyframes: {made} generated, {len(sb['shots']) * len(ratios) - made} cached")
