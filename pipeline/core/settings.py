"""Choices that belong to the person, not to one film. Kept with their films, so Git never sees them."""
import json

from . import config

DEFAULTS = {"writer": "auto", "voice": "addis"}


def file():
    return config.FILMS / "settings.json"


def load():
    try:
        saved = json.loads(file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS and isinstance(v, str)}} if isinstance(saved, dict) else dict(DEFAULTS)


def save(**changes):
    now = {**load(), **changes}
    config.FILMS.mkdir(parents=True, exist_ok=True)
    part = file().with_suffix(".part")
    part.write_text(json.dumps(now, indent=1) + "\n", encoding="utf-8", newline="\n")
    part.replace(file())
