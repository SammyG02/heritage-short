"""Script stage: turn a story, language and theme into a draft storyboard. A person edits and approves it."""
import copy
import json
import re
from datetime import datetime
from pathlib import Path

from . import narration
from .core import budget, config, providers, runlog, settings, storyboard
from .core.storyboard import require_consent, validate

LANGUAGES = {"am": "Amharic", "en": "English"}
COMING_SOON = ["Afaan Oromo", "Tigrinya", "Somali"]
THEMES = {
    "home": "Hospitality and home: warm amber and terracotta, firelight, intimate",
    "journey": "Journey and courage: wide landscapes, dawn light, dust and gold",
    "wisdom": "Wisdom and proverbs: quiet interiors, deep indigo and candlelight",
    "celebration": "Celebration and joy: bright festival colours, daylight, flowers",
    "memory": "Memory and loss: soft rain, muted blues, one warm light",
}
# Tried in order: Gemini 3.8 Flash was overloaded (503) in our first smoke test.
MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]

PROMPT = """You write storyboards for 60-90 second animated short films.

Story: {story}
Theme: {theme}
Audience: {audience}
Feeling at the end: {intent}
Narration languages: English{extra}

Rules:
- 8 to 10 shots, ids s01, s02 and so on. duration_s 6 to 9 each; total 62 to 80. The whole narration is 130 to 165 English words.
- One idea and one gentle movement per shot. Vary shot size.
- One or two invented main characters, the same people in every shot, with only a change of age or clothes the story needs. Never depict, name or identify a real person. No crowds.
- If a character is quoted, put only their words in quote marks (« » in Amharic, “ ” in English) in every language, and set quote_voice to that character. At most ONE quoted character in the film.
- Narration: one spoken line per shot by one narrator, 10 to 20 words, numbers written as words, natural in each language, not word-for-word translation.
- image_prompt: describe only what is visible. Say what is there; never use words like no, without or not. No written text in the image.
- motion_prompt: one small movement and a fixed camera, not the subject's appearance. Faces may speak, blink or smile; bodies move little.
- emotion: what the faces and bodies visibly feel in this shot, specific and true to this moment of the story; "quiet place, nobody visible" when nobody is seen.
- voice_emotion: how the narrator should sound on this line, a few words.
- transition: how this shot arrives from the one before, chosen for meaning: cut (shock or change), dissolve (time or memory), fadeblack (an ending, night, loss),
  fadewhite (birth, hope, revelation), smoothleft or smoothright (a journey), smoothup (rising), circleopen (a discovery). Give a one-sentence reason. Use cut for s01.
- Keep the surprise or turn of the story hidden in words AND pictures until its shot.
- reason: one sentence on why the shot exists.
- references: define only people or objects that appear in at least two shots, at most four. Give each a short lowercase name.
  Most stories need no second version of anyone. Add one (older, as a child, different clothes) ONLY if the story really shows that person at another time;
  give it "from": the name of the base person, and describe only the small change (for example "about ten years older, a few grey hairs"), never a different skin tone or face.

Return one JSON object with exactly these keys:
title (object: language code to text), logline, style_block (palette, light, medium that suit THIS story; no artist names), narrator_style (how the narrator should sound, for this story),
speakers: {{"name": {{"gender": "man, woman, boy or girl", "style": "how they speak"}}}} (empty object when nobody is quoted),
references: {{"name": {{"prompt": "portrait or still life...", "look": "one sentence: age, face, hair, clothes, colours", "from": "only for another version of a person"}}}},
music: {{"caption": "Instrumental ... the instruments, mood and place of THIS story ... no vocals", "bpm": integer 60-100, "key": "D minor"}},
shots: array of {{id, size (one of: extreme wide, wide, medium, medium close-up, close-up, insert), duration_s, references, reason, emotion, voice_emotion, transition (object: type, reason), quote_voice (only when quoted),
 image_prompt, motion_prompt, ken_burns (one of: in, out, left, right, up, down), narration: {{"en": "..."{narr}}}}}
"""


def _generate(prompt):
    return providers.write_json("script", "storyboard", prompt, settings.load()["writer"], MODELS)[0]


def build(draft, *, language, theme, audience, intent, base, narrator="man", people=None):
    """Fill the parts that are ours to decide (models, seeds, mix) around the model's draft. Nothing comes from another film."""
    title = draft["title"].get("en") or next(iter(draft["title"].values()))
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:28] or "story"
    people = people or {"real_people": False, "statement": "All characters are invented. The voices are stock synthetic voices."}
    # A true story starts with Google: Addis AI may train on what it is sent, and that needs its own yes.
    engine = "gemini" if people.get("based_on_real_people") else narration.default_engine(language)
    by_gender = base["voice_by_gender"]
    voice = {"voice": by_gender.get(narrator, by_gender["man"]), "style": draft.get("narrator_style") or "warm and natural, fitting the story", "model": base["models"]["tts"]}
    speakers = {k: {"voice": by_gender.get(v.get("gender"), by_gender["woman"]), "style": v.get("style") or "natural, fitting the moment"}
                for k, v in (draft.get("speakers") or {}).items()}
    for k in speakers:  # a character must not sound like the narrator
        if speakers[k]["voice"] == voice["voice"]:
            speakers[k]["voice"] = {"Algieba": "Charon", "Sulafat": "Kore"}.get(voice["voice"], "Puck")
    langs = list(dict.fromkeys([language, "en"]))
    references = {}
    for k, v in draft["references"].items():
        prompt = v["prompt"]
        if v.get("from"):
            prompt = f"The same person as in the reference image: same face shape, same eyes, same skin tone. Change only this: {prompt}"
        references[k] = {"prompt": prompt, "seeds": [11, 22], "chosen_seed": 11, "reason": "Not chosen yet", **{x: v[x] for x in ("look", "from") if v.get(x)}}
    ids = [s["id"] for s in draft["shots"]]
    # Every shot starts as a free camera move; the person chooses which ones really move, and on which service.
    shots = [{**s, "seed": 1000 + i, "motion": "camera", "narration": {k: s["narration"][k] for k in langs if k in s["narration"]}} for i, s in enumerate(draft["shots"], 1)]
    for s in shots:
        if not s.get("quote_voice"):
            s.pop("quote_voice", None)
    return {"id": f"{slug}-{datetime.now():%m%d%H%M%S}", "version": 1, "status": "draft", "title": draft["title"], "logline": draft["logline"], "theme": theme,
            "language": language, "audience": audience, "intent": intent, "style_block": draft["style_block"], "people": people,
            "models": copy.deepcopy(base["models"]), "voices": {k: addis_cast(base, k, narrator, draft, v) if engine == "addis" else v for k, v in ((k, {**copy.deepcopy(voice), **({"characters": copy.deepcopy(speakers)} if speakers else {})}) for k in langs)},
            "references": references, "video": copy.deepcopy(base["video"]), "picture_size": base["picture_size"],
            "music": {**base["music"], "caption": draft["music"]["caption"], "bpm": int(draft["music"]["bpm"]), "key": draft["music"]["key"],
                      "chosen_seed": base["music"]["seeds"][0], "reason": "Not chosen yet",
                      "cues": [{"shot": ids[0], "action": "start", "note": "Opens before the voice"}, {"shot": ids[-1], "action": "end", "note": "Returns and fades"}]},
            "mix": copy.deepcopy(base["mix"]), "approvals": {}, "shots": shots,
            "end_card": {"duration_s": base["end_card_seconds"], "lines": [*dict.fromkeys(draft["title"].values())][:2] + ["Pictures, voice and music made with AI",
                         "A true story. All faces are invented" if people.get("based_on_real_people") else "All characters are invented"]}}


def addis_cast(base, lang, narrator, draft, voice):
    """The same people with Addis AI's voices. Nobody quoted sounds like the narrator."""
    kinds = {"boy": "man", "girl": "woman"}
    pool = {k: list(v) for k, v in base["addis_voices"][lang].items()}
    take = lambda who: pool[kinds.get(who, who) if kinds.get(who, who) in pool else "woman"].pop(0)  # noqa: E731
    out = {**voice, "engine": "addis", "voice": take(narrator if narrator in pool else "man")}
    for name, c in (out.get("characters") or {}).items():
        c["voice"] = take((draft.get("speakers") or {}).get(name, {}).get("gender", "woman"))
    return out


def lint(sb):
    """Rules every film must meet that a JSON Schema cannot express."""
    problems = [f"{s['id']}: missing {k}" for s in sb["shots"] for k in ("emotion", "transition") if not s.get(k)]
    problems += [f"references/{n}: missing look" for n, r in sb["references"].items() if not r.get("look")]
    used = {n for s in sb["shots"] for n in s["references"]}
    problems += [f"references/{n}: no shot uses it" for n in sb["references"] if n not in used and n not in {r.get("from") for r in sb["references"].values()}]
    sizes = [s["size"] for s in sb["shots"]]
    problems += [f"{sb['shots'][i]['id']}: three shots in a row have the same size" for i in range(2, len(sizes)) if len(set(sizes[i - 2:i + 1])) == 1]
    for s in sb["shots"]:
        if len(s["narration"]["en"].split()) > 24:
            problems.append(f"{s['id']}: narration is too long for one shot")
    return problems


def limits(sb):
    """A new film must fit one day's voice allowance and 60-90 seconds before anything is made."""
    lang = sb["language"]
    calls = narration.calls_needed(sb, lang, sb["shots"])
    problems = [f"{calls} voice calls needed, the most is {budget.TTS_PER_DAY - 1}: use at most two speakers"] if calls > budget.TTS_PER_DAY - 1 else []
    length = narration.estimate_s(sb, lang)
    if not 61 <= length <= 88:
        problems.append(f"the narration would last about {length:.0f} seconds, it must be 61 to 88: {'shorten' if length > 88 else 'lengthen'} it")
    return problems + narration.text_problems(sb, lang)


PROOF = """You are a careful native {name} editor checking narration that a voice model will read aloud. Check spelling, grammar, agreement, natural
wording and words a voice could mispronounce. Do not rewrite style. Title: {title}
Lines: {lines}
Return JSON: {{"notes": [{{"shot": "s01", "problem": "...", "suggestion": "the corrected full line"}}]}} with only real problems, or an empty list."""


def proofread(sb, lang):
    """One text call. Suggestions only: a person decides."""
    require_consent(sb)
    storyboard.require_service(sb, "groq" if settings.load()["writer"].startswith("groq:") else "google")
    prompt = PROOF.format(name=LANGUAGES[lang], title=sb["title"].get(lang, ""), lines=json.dumps({s["id"]: s["narration"][lang] for s in sb["shots"]}, ensure_ascii=False))
    return _generate(prompt).get("notes", [])


def new(story, language, theme, audience, intent, true_story=False, consent_record="", narrator="man", people_agreed=None, ai_services=None):
    """Draft a storyboard, save it under storyboards/ and return (path, storyboard)."""
    if language not in LANGUAGES:
        raise config.PipelineError(f"Choose one of {', '.join(LANGUAGES)}. Coming soon: {', '.join(COMING_SOON)}.")
    if len(story.split()) < 12:
        raise config.PipelineError("Please tell the story in at least a few sentences.")
    if true_story and people_agreed is not None:  # the studio: one line per person and one box per AI service
        people_agreed = storyboard.clean_people(people_agreed)
        ai_services = {k: v is True for k, v in (ai_services or {}).items() if k in storyboard.AI_SERVICES}
        writer = "groq" if settings.load()["writer"].startswith("groq:") else "google"
        if not ai_services.get(writer):
            raise config.PipelineError(f"The script is written by {storyboard.AI_SERVICES[writer][0]}, which reads the story. Tick it only if they agreed.")
        consent_record = (storyboard.people_lines(people_agreed) + ("\n" + consent_record.strip() if consent_record.strip() else "")).strip()
    elif true_story and len(consent_record.split()) < 8:
        raise config.PipelineError("This is about real people, and the story is sent to an AI service to write the script. Record consent first: who agreed, when, how and to what.")
    audience, intent = audience.strip() or "the storyteller's family and friends", intent.strip() or "what the story itself calls for"
    theme_text = THEMES.get(theme, theme)
    base = json.loads((Path(__file__).parent / "defaults.json").read_text(encoding="utf-8"))
    people = None
    if true_story:
        people = {"real_people": False, "based_on_real_people": True, "consent": "recorded", "consent_record": consent_record.strip(),
                  **({"people_agreed": people_agreed, "ai_services": ai_services} if people_agreed else {}),
                  "statement": "Based on a true story. Faces are invented and voices are stock synthetic voices."}
    runlog.use_private()
    extra = f" and {LANGUAGES[language]}" if language != "en" else ""
    prompt = PROMPT.format(story=story, theme=theme_text, audience=audience, intent=intent, extra=extra,
                           narr=f', "{language}": "..."' if language != "en" else "")
    problems = []
    for _ in range(2):
        draft = _generate(prompt + (("\nYour last answer had these problems, fix them:\n" + "\n".join(problems)) if problems else ""))
        try:
            sb = build(draft, language=language, theme=theme_text, audience=audience, intent=intent, base=base, narrator=narrator, people=people)
            sb["story"] = story.strip()
            problems = validate(sb) or lint(sb) + limits(sb)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            problems = [f"missing or wrong field: {e}"]
        if not problems:
            p = config.FILMS / sb["id"] / "storyboard.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
            return p, sb
    raise config.PipelineError("The draft storyboard was not valid:\n  - " + "\n  - ".join(problems[:8]))


def interactive():
    print("Tell a story. Please leave out real names and private details.\n")
    story = input("Story (a few sentences): ").strip()
    print("Languages: " + ", ".join(f"{k} = {v}" for k, v in LANGUAGES.items()) + f"   (coming soon: {', '.join(COMING_SOON)})")
    language = input("Language [am]: ").strip() or "am"
    print("Themes:\n" + "\n".join(f"  {k}: {v}" for k, v in THEMES.items()))
    theme = input("Theme, or your own words [home]: ").strip() or "home"
    audience = input("Who is it for? [my family]: ").strip() or "my family"
    intent = input("What should they feel at the end? [close to home]: ").strip() or "close to home"
    return new(story, language, theme, audience, intent)
