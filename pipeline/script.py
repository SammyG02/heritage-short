"""Script stage: turn a story, language and theme into a draft storyboard. A person edits and approves it."""
import copy
import json
import re
from datetime import datetime

from .core import config, providers
from .core.storyboard import validate

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

PROMPT = """You write storyboards for 60-90 second hand-painted animated short films.

Story: {story}
Theme: {theme}
Audience: {audience}
Feeling at the end: {intent}
Narration languages: English{extra}

Rules:
- 9 to 11 shots, ids s01, s02 and so on. duration_s 5 to 8 each; total 60 to 80.
- One idea and one gentle movement per shot. Vary shot size.
- One or two invented main characters, the same people in every shot, with only a change of age or clothes the story needs. Never depict, name or identify a real person. No crowds.
- Narration: short spoken sentences, 8 to 16 words, natural in each language, not word-for-word translation.
- image_prompt: describe only what is visible. Say what is there; never use words like no, without or not. No written text in the image.
- motion_prompt: one small movement and a fixed camera, not the subject's appearance. Faces may speak, blink or smile; bodies move little.
- emotion: what the faces and bodies visibly feel in this shot, specific and true to this moment of the story; "quiet place, nobody visible" when nobody is seen.
- voice_emotion: how the narrator should sound on this line, a few words.
- transition: how this shot arrives from the one before, chosen for meaning: cut (shock or change), dissolve (time or memory), fadeblack (an ending, night, loss),
  fadewhite (birth, hope, revelation), smoothleft or smoothright (a journey), smoothup (rising), circleopen (a discovery). Give a one-sentence reason. Use cut for s01.
- Keep the surprise or turn of the story hidden in words AND pictures until its shot.
- reason: one sentence on why the shot exists.
- references: names from the references you define; "character" for shots showing the main character, "object" for shots showing the returning object.

Return one JSON object with exactly these keys:
title (object: language code to text), logline, style_block (palette, light, medium; hand-painted; no artist names),
references: {{"character": {{"prompt": "portrait...", "look": "one sentence: age, face, hair, clothes, colours"}}, "object": {{"prompt": "still life...", "look": "one sentence"}}}},
music: {{"caption": "Instrumental ... no vocals", "bpm": integer 60-100, "key": "D minor"}},
shots: array of {{id, size (one of: extreme wide, wide, medium, medium close-up, close-up, insert), duration_s, references, reason, emotion, voice_emotion, transition (object: type, reason),
 image_prompt, motion_prompt, ken_burns (one of: in, out, left, right, up, down), narration: {{"en": "..."{narr}}}}}
"""


def _generate(prompt):
    error = None
    for model in MODELS:
        try:
            return providers.gemini_json("script", "storyboard", prompt, model)
        except providers.ProviderError as e:
            error = e
            print(f"    {model} unavailable, trying the next model")
    raise error


def build(draft, *, language, theme, audience, intent, base):
    """Fill the parts that are ours to decide (models, seeds, mix) around the model's draft."""
    sb = copy.deepcopy(base)
    title = draft["title"].get("en") or next(iter(draft["title"].values()))
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:28] or "story"
    sb.update(id=f"{slug}-{datetime.now():%m%d%H%M}", version=1, status="draft", title=draft["title"], logline=draft["logline"],
              theme=theme, language=language, audience=audience, intent=intent, style_block=draft["style_block"])
    # The main TTS model allows about 10 free calls a day, fewer than one film can need.
    sb["voices"] = {k: {**base["voices"][k], "model": "gemini-3.8-flash-lite-tts"} for k in dict.fromkeys([language, "en"])}
    sb["references"] = {k: {"prompt": v["prompt"], "seeds": [11, 22, 33, 44], "chosen_seed": 11, "reason": "Not chosen yet", **({"look": v["look"]} if v.get("look") else {})}
                        for k, v in draft["references"].items()}
    ids = [s["id"] for s in draft["shots"]]
    sb["music"].update(caption=draft["music"]["caption"], bpm=int(draft["music"]["bpm"]), key=draft["music"]["key"], reason="Not chosen yet",
                       cues=[{"shot": ids[0], "action": "start", "note": "Opens before the voice"},
                             {"shot": ids[-1], "action": "end", "note": "Returns and fades"}])
    sb["shots"] = [{**s, "seed": 1000 + i} for i, s in enumerate(draft["shots"], 1)]
    for s in sb["shots"]:
        s["narration"] = {k: s["narration"][k] for k in sb["voices"] if k in s["narration"]}
    sb["end_card"]["lines"] = [*dict.fromkeys(draft["title"].values())][:2] + ["Pictures, voice and music made with AI", "A true story. All faces are invented" if sb["people"].get("based_on_real_people") else "All characters are invented"]
    return sb


def lint(sb):
    """Rules every film must meet that a JSON Schema cannot express."""
    problems = [f"{s['id']}: missing {k}" for s in sb["shots"] for k in ("emotion", "transition") if not s.get(k)]
    problems += [f"references/{n}: missing look" for n, r in sb["references"].items() if not r.get("look")]
    sizes = [s["size"] for s in sb["shots"]]
    problems += [f"{sb['shots'][i]['id']}: three shots in a row have the same size" for i in range(2, len(sizes)) if len(set(sizes[i - 2:i + 1])) == 1]
    for s in sb["shots"]:
        if len(s["narration"]["en"].split()) > 24:
            problems.append(f"{s['id']}: narration is too long for one shot")
    return problems


def new(story, language, theme, audience, intent, true_story=False):
    """Draft a storyboard, save it under storyboards/ and return (path, storyboard)."""
    if language not in LANGUAGES:
        raise config.PipelineError(f"Choose one of {', '.join(LANGUAGES)}. Coming soon: {', '.join(COMING_SOON)}.")
    if len(story.split()) < 12:
        raise config.PipelineError("Please tell the story in at least a few sentences.")
    theme_text = THEMES.get(theme, theme)
    base = json.loads((config.ROOT / "storyboard.json").read_text(encoding="utf-8"))
    base["people"] = {"real_people": False, "statement": "All characters are invented. The narrator is a stock synthetic voice."}
    if true_story:
        base["people"].update(based_on_real_people=True, consent="pending", statement="Based on a true story. Faces are invented and voices are stock synthetic voices.")
    extra = f" and {LANGUAGES[language]}" if language != "en" else ""
    prompt = PROMPT.format(story=story, theme=theme_text, audience=audience, intent=intent, extra=extra,
                           narr=f', "{language}": "..."' if language != "en" else "")
    problems = []
    for _ in range(2):
        draft = _generate(prompt + (("\nYour last answer had these problems, fix them:\n" + "\n".join(problems)) if problems else ""))
        try:
            sb = build(draft, language=language, theme=theme_text, audience=audience, intent=intent, base=base)
            problems = validate(sb) + lint(sb)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            problems = [f"missing or wrong field: {e}"]
        if not problems:
            p = config.ROOT / "storyboards" / f"{sb['id']}.json"
            p.parent.mkdir(exist_ok=True)
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
