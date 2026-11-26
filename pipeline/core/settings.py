"""Choices that belong to the person, not to one film. Kept with their films, so Git never sees them."""
import json

from . import config

DEFAULTS = {"writer": "auto", "voice": "addis", "wavespeed_budget": 1.0}  # USD the studio may spend on WaveSpeed, redos included ($1 of credit, 26 Nov)


def file():
    return config.FILMS / "settings.json"


def load():
    try:
        saved = json.loads(file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS and (isinstance(v, (int, float)) and not isinstance(v, bool) if isinstance(DEFAULTS[k], float) else isinstance(v, type(DEFAULTS[k])))}} if isinstance(saved, dict) else dict(DEFAULTS)


def save(**changes):
    now = {**load(), **changes}
    config.FILMS.mkdir(parents=True, exist_ok=True)
    part = file().with_suffix(".part")
    part.write_text(json.dumps(now, indent=1) + "\n", encoding="utf-8", newline="\n")
    part.replace(file())
