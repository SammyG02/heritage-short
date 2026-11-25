"""Load and validate the storyboard, the contract between every stage."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from . import config


def validate(data: dict) -> list[str]:
    schema = json.loads(config.SCHEMA.read_text(encoding="utf-8"))
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: str(list(e.absolute_path))):
        where = "/".join(map(str, e.absolute_path)) or "storyboard"
        errors.append(f"{where}: {e.message}")
    if errors:
        return errors
    ids = [s["id"] for s in data["shots"]]
    if len(ids) != len(set(ids)):
        errors.append("shots: ids must be unique")
    if data["language"] not in data["voices"]:
        errors.append(f"voices: no voice for the main language {data['language']!r}")
    for s in data["shots"]:
        for lang in data["voices"]:
            if not s["narration"].get(lang):
                errors.append(f"shots/{s['id']}/narration: missing {lang!r}")
            if s.get("quote_voice") and s["quote_voice"] not in data["voices"][lang].get("characters", {}):
                errors.append(f"shots/{s['id']}/quote_voice: no {lang!r} voice for {s['quote_voice']!r}")
        for ref in s["references"]:
            if ref not in data["references"]:
                errors.append(f"shots/{s['id']}/references: unknown reference {ref!r}")
    for name, ref in data["references"].items():
        if ref["chosen_seed"] not in ref["seeds"]:
            errors.append(f"references/{name}: chosen_seed must be one of seeds")
        parent = ref.get("from")
        if parent and (parent not in data["references"] or parent == name or data["references"][parent].get("from")):
            errors.append(f"references/{name}: 'from' must name a reference that is not itself derived")
    if data["music"]["chosen_seed"] not in data["music"]["seeds"]:
        errors.append("music: chosen_seed must be one of seeds")
    for cue in data["music"]["cues"]:
        if cue["shot"] not in ids:
            errors.append(f"music/cues: unknown shot {cue['shot']!r}")
    planned = sum(s["duration_s"] for s in data["shots"]) + data["end_card"]["duration_s"]
    if not 60 <= planned <= 90:
        errors.append(f"shots: planned length is {planned:.1f} s, must be 60-90 s")
    return errors


def load(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise config.PipelineError(f"Cannot read storyboard: {e}")
    except ValueError as e:
        raise config.PipelineError(f"{path} is not valid JSON: {e}")
    errors = validate(data)
    if errors:
        raise config.PipelineError("Storyboard is not valid:\n  - " + "\n  - ".join(errors))
    return data


def require_consent(data: dict) -> None:
    """Called before any model call. A true story stays locked until ETHICS.md holds the consent."""
    p = data["people"]
    if p.get("based_on_real_people") and p.get("consent") != "recorded":
        raise config.PipelineError("This storyboard tells a real person's story and consent is still pending. Record it in "
                                   "ETHICS.md, then set people.consent to 'recorded'.")


def out(data: dict, *parts: str) -> Path:
    return config.OUTPUTS.joinpath(data["id"], *parts)
