"""Keyframe stage: reference sheet first, then one image per shot and aspect ratio."""
import shutil

from . import narration
from .core import approvals, budget, cache, config, providers
from .core.storyboard import out, require_consent

# Multiples of 16, close to the delivery ratios.
SIZES = {"9x16": (768, 1344), "16x9": (1344, 768)}
LIGHT = {"9x16": (512, 896), "16x9": (896, 512)}  # still larger than the 480p clip made from it
NEURONS_OUT, NEURONS_IN = 26.05, 5.37  # FLUX.2 klein 4B per 512 px tile, Cloudflare price page, 25 Nov 2026
FRAMING = {"9x16": "tall vertical scene, subject large in the middle third, the painted scene continues down to the bottom edge",
           "16x9": "horizontal composition, subject in the centre, calm empty space near the bottom"}


def service(sb):
    """Where this film's shots are drawn: 'cloudflare' or 'kaggle'. The same model either way."""
    return (sb.get("services") or {}).get("pictures", "cloudflare")


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


def seed(shot, ratio):
    """Each format has its own take number, so redrawing one leaves the other alone."""
    return shot["seed"] + 1000 * shot.get("takes", {}).get(ratio, 0)


def size(sb, shot, ratio):
    light = sb.get("picture_size") == "light" and shot.get("motion", "clip") == "clip"
    return (LIGHT if light else SIZES)[ratio]


def cost(sb, shot, ratio):
    """Free units one picture uses."""
    w, h = size(sb, shot, ratio)
    return -(-w // 512) * -(-h // 512) * NEURONS_OUT + len(shot["references"]) * NEURONS_IN


def prompt(sb, shot, ratio):
    """The same locked description of each character goes into every shot that shows them."""
    looks = [f"Reference image {i} is the {n.replace('_', ' ')}: {sb['references'][n]['look']}. Same face, hair and clothes as reference image {i}"
             for i, n in enumerate(shot["references"], 1) if sb["references"][n].get("look")]
    bits = [f"{shot['size']} shot", shot["image_prompt"], *([f"Visible emotion: {shot['emotion']}"] if shot.get("emotion") else []),
            *looks, FRAMING[ratio], sb["style_block"]]
    return ". ".join(bits)


def inputs(sb, shot, ratio):
    refs = [ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in shot["references"]]
    return {"stage": "keyframe/1", "model": sb["models"]["image"], "seed": seed(shot, ratio), "size": list(size(sb, shot, ratio)),
            "prompt": prompt(sb, shot, ratio),
            # A missing reference never matches a cached key, so it is generated first.
            "references": [cache.file_sha(r) if r.exists() else "missing" for r in refs]}


def run_references(sb, force=False, only=None):
    made = 0
    for name, ref in sorted(sb["references"].items(), key=lambda kv: bool(kv[1].get("from"))):  # parents first
        if only and name not in only:
            continue
        for seed in ref["seeds"]:
            p, inp = ref_path(sb, name, seed), ref_inputs(sb, name, seed)
            if not force and cache.fresh(p, inp):
                continue
            require_consent(sb)
            base = [ref_path(sb, ref["from"], sb["references"][ref["from"]]["chosen_seed"])] if ref.get("from") else []
            data = providers.flux("references", f"{name}_{seed}", inp["prompt"], *inp["size"], seed, inp["model"], base)
            keep_version(p)
            cache.store(p, data, inp)
            made += 1
    print(f"  references: {made} generated")


def voice_ok(sb, shot):
    return approvals.ok(sb, "voice", shot["id"], narration.approval_key(sb, shot, sb["language"]))


def cast_ready(sb, shot):
    """Every face in the shot is drawn, up to date and chosen."""
    return all(sb["references"][n]["reason"] != "Not chosen yet"
               and cache.fresh(ref_path(sb, n, sb["references"][n]["chosen_seed"]), ref_inputs(sb, n, sb["references"][n]["chosen_seed"])) for n in shot["references"])


def version_number(v):
    n = v.stem.rsplit("_", 1)[1]
    return int(n) if n.isdigit() else 0


def versions(p):
    """Earlier pictures, oldest first."""
    return sorted((p.parent / "versions").glob(p.stem + "_*.png"), key=version_number)


def keep_version(p):
    """Never lose a paid-for picture: the old one moves to versions/ before a new one replaces it."""
    if p.exists():
        folder = p.parent / "versions"
        folder.mkdir(exist_ok=True)
        last = max((version_number(v) for v in versions(p)), default=0)
        shutil.copy2(p, folder / f"{p.stem}_{last + 1}.png")


def restore(sb, shot, ratio, name):
    """Bring an earlier picture back. It becomes the current picture for the shot as it is written now."""
    p = path(sb, shot, ratio)
    old = p.parent / "versions" / name
    if old.parent != p.parent / "versions" or not name.startswith(p.stem + "_") or not old.is_file():
        raise config.PipelineError("That version does not exist.")
    data = old.read_bytes()
    keep_version(p)
    cache.store(p, data, inputs(sb, shot, ratio), qa={"status": "restored by the filmmaker", "seed_used": None, "tries": []})
    old.unlink()


def run(sb, ratios=tuple(SIZES), force=False, only=None):
    from . import qa  # qa needs this module
    made, waiting, extra = 0, [], [qa.EXTRA_PER_RUN]
    todo = [s for s in sb["shots"] if not only or s["id"] in only]
    for shot in todo:
        for ratio in ratios:
            p, inp = path(sb, shot, ratio), inputs(sb, shot, ratio)
            if not force and cache.fresh(p, inp):
                continue
            require_consent(sb)
            if not voice_ok(sb, shot):
                waiting.append(shot["id"])
                continue
            if p.exists() and sb.get("approvals", {}).get("picture", {}).get(p.stem) == cache.file_sha(p) and cache.fresh(p, inp):
                raise config.PipelineError(f"{p.stem} is approved and locked.")
            if budget.flux_left() < cost(sb, shot, ratio):
                raise config.PipelineError(f"Stopped before the picture limit. {made} drawn and saved; run again after {budget.local(budget.flux_reset())}.")
            refs = [ref_path(sb, n, sb["references"][n]["chosen_seed"]) for n in shot["references"]]
            if gone := [n for n, r in zip(shot["references"], refs) if not cache.fresh(r, ref_inputs(sb, n, sb["references"][n]["chosen_seed"]))]:
                raise config.PipelineError(f"{shot['id']} needs a character that is not drawn yet, or whose face has changed: {', '.join(gone)}")
            data, report = qa.best_of(sb, shot, ratio, inp, refs, extra)
            keep_version(p)
            cache.store(p, data, inp, qa=report)
            made += 1
            print(f"  keyframe {shot['id']}_{ratio}")
    print(f"  keyframes: {made} generated, {len(todo) * len(ratios) - made} cached")
    if waiting:
        print("  waiting for voice approval: " + ", ".join(dict.fromkeys(waiting)))
