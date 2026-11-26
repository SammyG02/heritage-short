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
    p = data["people"]
    photos = {r["photo"]["person"] for r in data["references"].values() if r.get("photo")}
    agreed = {x["role"] for x in p.get("people_agreed", []) if x.get("photo")}
    if p.get("real_people") and not photos:
        errors.append("people: real_people is true, but no character is drawn from a photo")
    if photos and not (p.get("real_people") and p.get("based_on_real_people") and photos <= agreed):
        errors.append("references: a character is drawn from a photo without that person's recorded consent to it")
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


# What each service receives, said plainly; the studio shows these beside the boxes.
AI_SERVICES = {
    "google": ("Google Gemini", "the script, the voice lines and pictures to check"),
    "cloudflare": ("Cloudflare", "picture descriptions, to draw the pictures"),
    "addis": ("Addis AI", "the narration, to read it aloud; it may train on it"),
    "kaggle": ("Kaggle", "pictures and descriptions, for moving clips and music on its free GPU"),
    "wavespeed": ("WaveSpeed", "pictures and movement words, for paid moving clips; kept up to 7 days"),
    "groq": ("Groq", "pictures to check, only if chosen for checking"),
}


AGREED_TO = {"story": "their story told", "likeness": "drawn as a character", "words": "their words quoted", "photo": "their photo used as a reference"}
PHOTO_NOTE = "Some characters are drawn from family photos, each with that person's recorded consent; the others are invented."


def clean_people(rows) -> list:
    """Each person in a true story, by role: what they agreed to, and when and how. Refuses anything incomplete."""
    if not isinstance(rows, list) or not rows:
        raise config.PipelineError("Add at least one person who agreed.")
    out = []
    for r in rows:
        role, how = str((r or {}).get("role") or "").strip(), str((r or {}).get("how") or "").strip()
        if not role and not how:
            continue  # an empty row the person did not fill in
        if not role or len(role) > 40:
            raise config.PipelineError("Give each person a role, not a name: mother, brother, grandfather.")
        if len(how.split()) < 3:
            raise config.PipelineError(f"Say when and how the {role} agreed, for example: in person, 26 November.")
        agreed = {k: r.get(k) is True for k in AGREED_TO}
        if not any(agreed.values()):
            raise config.PipelineError(f"Tick what the {role} agreed to.")
        out.append({"role": role, **agreed, "how": how})
    if not out:
        raise config.PipelineError("Add at least one person who agreed.")
    return out


def people_lines(rows) -> str:
    return "\n".join(f"{r['role'].capitalize()}: agreed to {', '.join(v for k, v in AGREED_TO.items() if r[k])}; {r['how']}." for r in rows)


def require_service(data: dict, service: str) -> None:
    """A true story goes only to the services its people agreed to, ticked one by one on the Story tab."""
    p = data["people"]
    if p.get("based_on_real_people") and "ai_services" in p and not p["ai_services"].get(service):
        raise config.PipelineError(f"The people in this true story have not agreed to {AI_SERVICES[service][0]}. "
                                   "Tick it on the Story tab, under Consent, only if they did.")


def allowed(data: dict, service: str) -> bool:
    try:
        require_service(data, service)
        return True
    except config.PipelineError:
        return False


def root(film_id: str) -> Path:
    """Where a film keeps everything it makes: its own personal folder, or outputs/ for the film that belongs to this repository."""
    mine = config.FILMS / film_id
    return mine if (mine / "storyboard.json").is_file() else config.OUTPUTS / film_id


def out(data: dict, *parts: str) -> Path:
    return root(data["id"]).joinpath(*parts)
