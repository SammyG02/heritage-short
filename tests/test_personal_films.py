"""Each person's stories stay on their computer, and no film shapes another."""
import json
import re
import subprocess

import pytest

from pipeline import gpu, keyframes, narration, script, shots, web
from pipeline.core import budget, cache, config, providers, runlog, storyboard
from tests.conftest import BOARD


def draft(title="Two Rivers", people=("ana", "tom"), quoted=None, older=False):
    refs = {p: {"prompt": f"portrait of {p}", "look": f"{p} in a red coat"} for p in people}
    if older:
        refs[people[0] + "_old"] = {"prompt": "about ten years older, a few grey hairs", "look": "older", "from": people[0]}
    sizes = ["wide", "medium", "close-up"]
    out = []
    for i in range(9):
        use = [people[i % len(people)]] + ([people[0] + "_old"] if older and i > 6 else [])
        out.append({"id": f"s{i + 1:02}", "reason": "r", "duration_s": 7, "size": sizes[i % 3], "references": use, "image_prompt": "a boat", "motion_prompt": "it drifts",
                    "ken_burns": "in", "emotion": "calm", "voice_emotion": "soft", "transition": {"type": "cut", "reason": "r"},
                    "narration": {"en": "She crossed the wide river every morning before the town had even opened its eyes.",
                                  "am": "በየጠዋቱ ከተማው ከመንቃቱ በፊት ሰፊውን ወንዝ ትሻገር ነበር።"}})
    if quoted:
        out[3]["quote_voice"] = quoted
        out[3]["narration"] = {"en": "She said: “I will come back before the rain does.”", "am": "አለች፦ «ዝናቡ ሳይመጣ በፊት እመለሳለሁ።»"}
    return {"title": {"en": title, "am": "ሁለት ወንዞች"}, "logline": "l", "style_block": "ink and water", "narrator_style": "bright", "references": refs,
            "speakers": {quoted: {"gender": "woman", "style": "firm"}} if quoted else {}, "music": {"caption": "Instrumental flute, no vocals", "bpm": 90, "key": "G major"}, "shots": out}


def make(monkeypatch, **k):
    narrator = k.pop("narrator", "man")
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **kw: draft(**k))
    return script.new("word " * 20, "am", "home", "family", "close", narrator=narrator)


def test_the_code_knows_nothing_about_any_one_story():
    sb = json.loads(BOARD.read_text(encoding="utf-8"))
    words = {sb["id"], sb["title"]["en"], sb["title"]["am"], "Israel", "እስራኤል", *sb["references"]} - {"mother", "father"}
    for f in [*config.ROOT.glob("pipeline/**/*.py"), *config.ROOT.glob("pipeline/**/*.js"), *config.ROOT.glob("pipeline/*.json"), *config.ROOT.glob("schema/*")]:
        text = f.read_text(encoding="utf-8")
        for w in words:
            assert w not in text, (f.name, w)
    defaults = (config.ROOT / "pipeline" / "defaults.json").read_text(encoding="utf-8")
    for key in ("style_block", "references", "narration", "caption", "title"):
        assert f'"{key}"' not in defaults


def test_a_new_film_is_saved_with_the_person_not_with_the_code(monkeypatch):
    p, sb = make(monkeypatch)
    assert p == config.FILMS / sb["id"] / "storyboard.json"
    assert storyboard.validate(sb) == []
    for made in (narration.path(sb, sb["shots"][0], "am"), keyframes.path(sb, sb["shots"][0], "9x16"), shots.wan_path(sb, sb["shots"][0], "9x16")):
        assert config.FILMS / sb["id"] in made.parents


def test_git_never_sees_personal_films():
    r = subprocess.run(["git", "check-ignore", "my-films/some-film/storyboard.json", "my-films/runs.jsonl"], cwd=config.ROOT, capture_output=True, text=True)
    if r.returncode == 128:
        pytest.skip("not a git checkout")
    assert len(r.stdout.split()) == 2


def test_personal_calls_are_logged_with_the_person_and_still_count(monkeypatch):
    runlog.use_private()
    with runlog.call("narration", "am/s01", "gemini", "x-tts", {"text": "my private line"}):
        pass
    assert not config.RUNS.exists()
    assert "my private line" in (config.FILMS / "runs.jsonl").read_text(encoding="utf-8")
    assert budget.tts_left("x-tts") == budget.TTS_PER_DAY - 1


def test_two_stories_share_no_characters_music_voices_or_style(monkeypatch):
    _, a = make(monkeypatch, title="Two Rivers", people=("ana", "tom"))
    _, b = make(monkeypatch, title="The Clock", people=("bird", "king"))
    assert a["id"] != b["id"] and not set(a["references"]) & set(b["references"])
    for s in a["shots"]:
        assert set(s["references"]) <= set(a["references"])
    mine = json.loads(BOARD.read_text(encoding="utf-8"))
    for key in ("style_block", "references", "title", "audience"):
        assert a[key] != mine[key]
    assert a["music"]["caption"] != mine["music"]["caption"] and a["voices"]["am"]["style"] != mine["voices"]["am"]["style"]


def test_no_older_version_unless_the_script_has_one(monkeypatch):
    _, plain = make(monkeypatch)
    assert not any(r.get("from") for r in plain["references"].values())
    _, aged = make(monkeypatch, older=True)
    ref = aged["references"]["ana_old"]
    assert ref["from"] == "ana" and "same skin tone" in ref["prompt"] and "Change only this" in ref["prompt"]


def test_an_unused_character_is_rejected(monkeypatch):
    d = draft()
    d["references"]["nobody"] = {"prompt": "p", "look": "l"}
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: d)
    with pytest.raises(config.PipelineError, match="nobody"):
        script.new("word " * 20, "am", "home", "family", "close")


@pytest.mark.parametrize("narrator", ["man", "woman"])
def test_voices_follow_the_people_in_the_story(monkeypatch, narrator):
    _, sb = make(monkeypatch, quoted="ana", narrator=narrator)
    v = sb["voices"]["am"]
    genders = dict(web.GEMINI_VOICES)
    assert genders[v["voice"]] == narrator and genders[v["characters"]["ana"]["voice"]] == "woman"
    assert v["voice"] != v["characters"]["ana"]["voice"]
    assert narration.one_call(sb, "am", sb["shots"])


def test_moving_shots_are_drawn_small_and_still_shots_full(monkeypatch):
    _, sb = make(monkeypatch)
    s = sb["shots"][0]
    small = keyframes.cost(sb, s, "9x16")
    assert keyframes.inputs(sb, s, "9x16")["size"] == [512, 896]
    s["motion"] = "camera"
    assert keyframes.inputs(sb, s, "9x16")["size"] == [768, 1344]
    assert small < keyframes.cost(sb, s, "9x16") / 2.5
    for r in keyframes.SIZES:
        assert min(keyframes.LIGHT[r]) >= min(shots.WAN_SIZE[r]) and all(x % 16 == 0 for x in keyframes.LIGHT[r])


def test_films_made_before_this_keep_their_picture_size():
    sb = json.loads(BOARD.read_text(encoding="utf-8"))
    assert keyframes.size(sb, sb["shots"][0], "9x16") == (768, 1344)


def test_the_repository_film_is_hidden_unless_its_author_turns_it_on(monkeypatch):
    assert web.index() == {}
    _, sb = make(monkeypatch)
    assert list(web.index()) == [sb["id"]]
    monkeypatch.setenv("SHOW_REPO_FILM", "1")
    assert len(web.index()) > 1


def test_gpu_pictures_wait_for_the_same_approvals(monkeypatch):
    _, sb = make(monkeypatch)
    monkeypatch.setattr(gpu, "_push_kernel", lambda *a: pytest.fail("sent"))
    assert gpu.submit_pictures(sb) is None
    sb["people"].update(based_on_real_people=True, consent="pending")
    with pytest.raises(config.PipelineError, match="consent"):
        gpu.submit_pictures(sb)


def test_gpu_pictures_are_sent_and_collected(monkeypatch, tmp_path):
    from PIL import Image
    _, sb = make(monkeypatch)
    sb.pop("approvals")
    for name, ref in sb["references"].items():
        ref["reason"] = "chosen"
        for seed in ref["seeds"]:
            p = keyframes.ref_path(sb, name, seed)
            p.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32)).save(p)
            cache.stamp(p, keyframes.ref_inputs(sb, name, seed))
    sent = {}
    monkeypatch.setattr(gpu, "_push_dataset", lambda folder, job, name: sent.update(files=sorted(f.name for f in folder.iterdir()), name=name) or "ref")
    monkeypatch.setattr(gpu, "_push_kernel", lambda kind, code, ds=(): sent.update(code=code) or "me/k")
    gpu.submit_pictures(sb, ("9x16",), ["s01"])
    assert "job.json" in sent["files"] and "ana_11.jpg" in sent["files"] and "@@" not in sent["code"]
    compile(sent["code"], "w", "exec")
    job = json.loads(storyboard.out(sb, "jobs", "pictures.json").read_text(encoding="utf-8"))["job"]["pictures"][0]

    def output(*a, **k):
        folder = next(x for i, x in enumerate(a) if a[i - 1] == "-p")
        Image.new("RGB", (8, 8)).save(folder + "/s01_9x16.png" if isinstance(folder, str) else folder / "s01_9x16.png")
        rows = [{"event": "loaded", "seconds": 1}, {"event": "picture", "item": "s01_9x16", "key": job["key"], "status": "ok", "seconds": 30}, {"event": "done", "seconds": 40}]
        (type(config.ROOT)(folder) / "results.jsonl").write_text("\n".join(map(json.dumps, rows)))
    monkeypatch.setattr(gpu, "kaggle", output)
    gpu.fetch(sb, "pictures")
    s = sb["shots"][0]
    assert cache.fresh(keyframes.path(sb, s, "9x16"), keyframes.inputs(sb, s, "9x16"))
    assert cache.read_meta(keyframes.path(sb, s, "9x16"))["qa"]["status"].startswith("unchecked")


def test_several_jobs_can_wait_and_be_cancelled(monkeypatch):
    sb = json.loads(BOARD.read_text(encoding="utf-8"))
    for r in sb["references"].values():
        r["reason"] = "chosen"
    monkeypatch.setattr(web, "open_board", lambda fid: (None, sb))
    web.plan_later("x", {"action": "pictures", "shots": ["s01"], "ratios": ["9x16"]})
    web.plan_later("x", {"action": "voice"})
    web.plan_later("x", {"action": "voice"})
    assert sorted(p["action"] for p in web.plan_state()) == ["pictures", "voice"]
    web.cancel_plan()
    assert web.plan_state() == []


def test_ids_cannot_leave_the_films_folder():
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", "../secret") is None


def test_a_film_can_be_started_without_saying_who_it_is_for(monkeypatch):
    calls = []
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: calls.append(1) or draft())
    _, sb = script.new("word " * 20, "am", "home", "", " ")
    assert (sb["audience"], sb["intent"], len(calls)) == ("my family", "close to home", 1)
