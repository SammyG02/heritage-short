"""One test for each defect found in the code review of 25 Nov 2026, and for what its fix must not break."""
import copy
import io
import json
import wave

import pytest
from PIL import Image

from pipeline import __main__ as cli
from pipeline import assemble, gpu, keyframes, narration, qa, script, shots, web
from pipeline.core import approvals, cache, config, providers
from tests.conftest import BOARD


@pytest.fixture
def sb(monkeypatch, tmp_path):
    data = json.loads(BOARD.read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(narration, "estimate_s", lambda *a: 80)
    data["people"]["consent"] = "recorded"
    for ref in data["references"].values():
        ref["reason"] = "chosen"
    return data


def wav(level=4000, seconds=0.5):
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(int(level).to_bytes(2, "little", signed=True) * int(24000 * seconds))
    return raw.getvalue()


def png(colour=0):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (colour, 0, 0)).save(buf, "PNG")
    return buf.getvalue()


def voices(sb, level=4000):
    for s in sb["shots"]:
        cache.store(narration.path(sb, s, "am"), wav(level), narration.inputs(sb, s, "am"))


def cast(sb):
    for name, ref in sorted(sb["references"].items(), key=lambda kv: bool(kv[1].get("from"))):
        for seed in ref["seeds"]:
            cache.store(keyframes.ref_path(sb, name, seed), png(seed), keyframes.ref_inputs(sb, name, seed))


def ok_voice(sb, s):
    approvals.give(sb, "voice", s["id"], narration.approval_key(sb, s, "am"))


def picture(sb, s, ratio, colour=1):
    cache.store(keyframes.path(sb, s, ratio), png(colour), keyframes.inputs(sb, s, ratio))


# 1 ---------------------------------------------------------------- redraw one format only
def test_redrawing_one_format_leaves_the_other_and_its_clip_alone(sb):
    s = sb["shots"][2]
    cast(sb)
    for r in keyframes.SIZES:
        picture(sb, s, r)
        cache.store(shots.wan_path(sb, s, r), b"clip", shots.wan_inputs(sb, s, r))
    approvals.give(sb, "picture", "s03_16x9", cache.file_sha(keyframes.path(sb, s, "16x9")))
    web.new_take(s, "9x16")
    assert not cache.fresh(keyframes.path(sb, s, "9x16"), keyframes.inputs(sb, s, "9x16"))
    assert cache.fresh(keyframes.path(sb, s, "16x9"), keyframes.inputs(sb, s, "16x9"))
    assert shots.has_wan(sb, s, "16x9")
    first = keyframes.inputs(sb, s, "9x16")["seed"]
    web.new_take(s, "9x16")
    assert keyframes.inputs(sb, s, "9x16")["seed"] != first
    from pipeline.core import storyboard
    assert storyboard.validate(sb) == []


# 2 ---------------------------------------------------------------- pauses only between shots
def test_one_call_asks_for_pauses_between_shots_and_not_inside_them(monkeypatch):
    sent = {}

    class R:
        ok = True

        def json(self):
            import base64
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;rate=24000", "data": base64.b64encode(b"\0\0").decode()}}]}}]}
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(providers.requests, "post", lambda url, **k: sent.update(k["json"]) or R())
    turns = [{"speaker": "Narrator", "text": "ONE", "pause": True, "style": "calm"}, {"speaker": "Narrator", "text": "SHE SAYS", "pause": False, "style": "calm"},
             {"speaker": "Mother", "text": "QUOTE", "pause": True, "style": "proud"}, {"speaker": "Narrator", "text": "LAST", "pause": True, "style": "calm"}]
    providers.gemini_take("n", "i", turns, {"Narrator": {"voice": "A", "style": "x"}, "Mother": {"voice": "B", "style": "y"}}, "gemini-3.1-flash-tts-preview")
    script_text = sent["contents"][0]["parts"][0]["text"].split("SCRIPT", 1)[1]
    blocks = [b for b in script_text.split("\n\n") if any(w in b for w in ("ONE", "SAYS", "QUOTE", "LAST"))]
    assert len(blocks) == 3 and "SHE SAYS" in blocks[1] and "QUOTE" in blocks[1]


# 3 ---------------------------------------------------------------- derived faces follow their base
def test_a_stale_older_face_is_never_drawn_into_a_shot(sb, monkeypatch):
    cast(sb)
    voices(sb)
    s = next(x for x in sb["shots"] if "mother_older" in x["references"])
    ok_voice(sb, s)
    monkeypatch.setattr(providers, "flux", lambda *a, **k: pytest.fail("drew with an old face"))
    other = next(x for x in sb["references"]["mother"]["seeds"] if x != sb["references"]["mother"]["chosen_seed"])
    sb["references"]["mother"]["chosen_seed"] = other
    with pytest.raises(config.PipelineError, match="mother_older"):
        keyframes.run(sb, ("9x16",), only=[s["id"]])


def test_changing_a_base_face_reopens_its_older_versions(sb):
    web.choose_face(sb, "mother", 22, "new")
    assert sb["references"]["mother"]["chosen_seed"] == 22
    assert sb["references"]["mother_older"]["reason"] == "Not chosen yet"
    assert sb["references"]["father_older"]["reason"] == "chosen"
    sb["references"]["mother_older"]["reason"] = "chosen"
    web.choose_face(sb, "mother", 22, "same face again")
    assert sb["references"]["mother_older"]["reason"] == "chosen"


# 4 ---------------------------------------------------------------- no picture is ever lost
def test_no_version_is_lost_after_restoring_one(sb):
    s = sb["shots"][0]
    p = keyframes.path(sb, s, "9x16")
    for colour in (1, 2, 3, 4):
        keyframes.keep_version(p)
        picture(sb, s, "9x16", colour)
    folder = p.parent / "versions"
    oldest = min(folder.glob("*.png"), key=lambda f: int(f.stem.rsplit("_", 1)[1]))
    keyframes.restore(sb, s, "9x16", oldest.name)
    for colour in (5, 6):
        keyframes.keep_version(p)
        picture(sb, s, "9x16", colour)
    have = {f.read_bytes() for f in [p, *folder.glob("*.png")]}
    assert have == {png(c) for c in (1, 2, 3, 4, 5, 6)}


def test_restore_refuses_other_files(sb):
    s = sb["shots"][0]
    picture(sb, s, "9x16")
    for name in ("../s01_9x16.png", "s02_9x16_1.png", "nope"):
        with pytest.raises(config.PipelineError):
            keyframes.restore(sb, s, "9x16", name)


# 5 ---------------------------------------------------------------- a planning limit is not part of a clip
def test_the_gpu_hours_limit_does_not_make_clips_stale(sb):
    s = sb["shots"][0]
    cache.store(shots.wan_path(sb, s, "9x16"), b"clip", shots.wan_inputs(sb, s, "9x16"))
    sb["video"]["max_gpu_hours"] = 3
    assert shots.has_wan(sb, s, "9x16")
    sb["video"]["steps"] += 1
    assert not shots.has_wan(sb, s, "9x16")


# 6 ---------------------------------------------------------------- a failed GPU job can be sent again
@pytest.mark.parametrize("action", ["motion_submit", "music_submit", "voice_submit"])
def test_an_uncollected_job_is_protected_but_can_be_replaced(sb, monkeypatch, tmp_path, action):
    kind = {"motion_submit": "wan", "music_submit": "music", "voice_submit": "voice"}[action]
    folder = tmp_path / "outputs" / "one-percent" / "jobs"
    folder.mkdir(parents=True)
    (folder / f"{kind}.json").write_text(json.dumps({"submitted": 1, "job": {}, "logged": ["loaded"]}))
    started = []
    monkeypatch.setattr(web, "open_board", lambda fid: (tmp_path / "x.json", sb))
    monkeypatch.setattr(web, "running", lambda: False)
    monkeypatch.setattr(web.subprocess, "Popen", lambda *a, **k: started.append(a))
    with pytest.raises(web.Refused, match="not been collected"):
        web.start("one-percent", action, {})
    assert started == []
    web.start("one-percent", action, {"replace": True})
    assert len(started) == 1
    web.job.clear()


def test_the_studio_offers_to_send_again_wherever_it_offers_to_collect():
    js = (web.STATIC / "app.js").read_text(encoding="utf-8")
    for collect in ("motion_fetch", "music_fetch", "voice_fetch"):
        near = js[js.index(f"run('{collect}')"):][:600]
        assert "sendAgain(" in near, collect


# 7 ---------------------------------------------------------------- consent before any model call
def test_proofreading_waits_for_consent(sb, monkeypatch):
    sb["people"].update(based_on_real_people=True, consent="pending")
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: pytest.fail("sent a true story"))
    with pytest.raises(config.PipelineError, match="consent"):
        script.proofread(sb, "am")


def test_drafting_a_true_story_waits_for_consent(monkeypatch):
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: pytest.fail("sent a true story"))
    story = "word " * 20
    for record in ("", "yes"):
        with pytest.raises(config.PipelineError, match="consent"):
            script.new(story, "am", "home", "family", "close", true_story=True, consent_record=record)


# 8 ---------------------------------------------------------------- approval is of the sound that was heard
def test_a_new_recording_needs_a_new_approval(sb):
    s = sb["shots"][0]
    voices(sb, 4000)
    ok_voice(sb, s)
    assert keyframes.voice_ok(sb, s)
    cache.store(narration.path(sb, s, "am"), wav(5000), narration.inputs(sb, s, "am"))
    assert not keyframes.voice_ok(sb, s)


def test_an_approval_does_not_count_without_a_current_voice(sb):
    s = sb["shots"][0]
    sb["approvals"]["voice"] = {}
    assert not keyframes.voice_ok(sb, s)
    voices(sb)
    ok_voice(sb, s)
    s["narration"]["am"] += " አዎ"
    assert not keyframes.voice_ok(sb, s)
    s["narration"]["am"] = s["narration"]["am"][:-3]
    assert keyframes.voice_ok(sb, s)


def test_films_made_before_approvals_are_still_open(sb):
    sb.pop("approvals")
    assert keyframes.voice_ok(sb, sb["shots"][0])


def test_the_approvals_already_given_still_count():
    sb = json.loads(BOARD.read_text(encoding="utf-8"))
    for sid in sb["approvals"]["voice"]:
        s = next(x for x in sb["shots"] if x["id"] == sid)
        if cache.fresh(narration.path(sb, s, "am"), narration.inputs(sb, s, "am")):
            assert keyframes.voice_ok(sb, s), sid


# 9 ---------------------------------------------------------------- emotion reaches the one-call voice
def test_each_lines_emotion_reaches_the_one_call_recording(sb, monkeypatch):
    for s in sb["shots"]:
        s.pop("tts_model", None)
    sb["shots"][1]["voice_emotion"] = "weary and slow"
    seen = []
    monkeypatch.setattr(providers, "gemini_take", lambda stage, item, turns, v, model: seen.extend(turns) or wav())
    with pytest.raises(config.PipelineError):
        narration.take(sb, "am", sb["shots"])
    assert "weary and slow" in seen[1]["style"] and "weary" not in seen[0]["style"]


# 10 --------------------------------------------------------------- film stops before spending or exporting
def test_film_stops_when_pictures_are_waiting(sb, monkeypatch):
    cast(sb)
    voices(sb)
    sb["approvals"]["voice"] = {}
    monkeypatch.setattr(gpu, "submit_music", lambda *a: pytest.fail("spent GPU time"))
    monkeypatch.setattr(gpu, "submit_wan", lambda *a, **k: pytest.fail("spent GPU time"))
    monkeypatch.setattr(assemble, "film", lambda *a: pytest.fail("built an incomplete film"))
    for use_gpu in (True, False):
        with pytest.raises(config.PipelineError, match="Not ready"):
            cli.film(sb, "am", use_gpu)


def test_film_still_builds_when_everything_is_ready(sb, monkeypatch):
    cast(sb)
    voices(sb)
    for s in sb["shots"]:
        for r in keyframes.SIZES:
            picture(sb, s, r)
    built = []
    monkeypatch.setattr(assemble, "film", lambda *a: built.append(a))
    cli.film(sb, "am", False)
    assert built


def test_a_whole_film_still_goes_through_every_gate_in_order(sb, monkeypatch):
    """The path a person follows: script, voice, cast, pictures, then motion."""
    drawn = []
    sb["approvals"] = {}
    cast(sb)
    monkeypatch.setattr(providers, "flux", lambda *a, **k: drawn.append(a[1]) or png(len(drawn) % 250))
    monkeypatch.setattr(qa, "check", lambda *a: {**dict.fromkeys(qa.KEYS, 9), "worst": 9, "problem": "none"})
    voices(sb)
    keyframes.run(sb)
    assert drawn == []
    for s in sb["shots"]:
        ok_voice(sb, s)
    keyframes.run(sb)
    assert len(drawn) == 12  # vertical only: the wide film is made from it
    assert shots.plan(sb)[0] == []
    for s in sb["shots"]:
        for r in keyframes.drawn(sb):
            p = keyframes.path(sb, s, r)
            approvals.give(sb, "picture", p.stem, cache.file_sha(p))
    assert shots.plan(sb, hours=8)[0]
    before = copy.deepcopy(drawn)
    keyframes.run(sb)
    assert drawn == before


# the brief's own requirements ---------------------------------------
def _stranger(sb, monkeypatch, calls):
    from pipeline.core import budget
    monkeypatch.setattr(budget, "flux_left", lambda: 99999)
    monkeypatch.setattr(providers, "gemini_take", lambda stage, item, turns, v, m: (_ for _ in ()).throw(providers.ProviderError("busy")))
    monkeypatch.setattr(budget, "tts_left", lambda m: 99)
    monkeypatch.setattr(providers, "gemini_tts", lambda stage, item, *a: calls.append(("voice", item)) or wav(4000, 3))
    monkeypatch.setattr(providers, "flux", lambda stage, item, *a, **k: calls.append(("picture", item)) or png(len(calls) % 250))
    monkeypatch.setattr(qa, "check", lambda *a: None)
    monkeypatch.setattr(assemble, "film", lambda *a: calls.append(("film", "built")))


def _command(monkeypatch, tmp_path, sb, *args):
    p = tmp_path / "board.json"
    p.write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    return cli.main(["-s", str(p), *args])


def test_a_stranger_rebuilds_the_film_with_one_command(sb, monkeypatch, tmp_path):
    calls = []
    _stranger(sb, monkeypatch, calls)
    assert _command(monkeypatch, tmp_path, sb, "film") == 0
    assert calls[-1] == ("film", "built") and sum(c[0] == "picture" for c in calls) == 12 + 12
    calls.clear()
    assert _command(monkeypatch, tmp_path, sb, "film") == 0
    assert calls == [("film", "built")]


@pytest.mark.parametrize("change,expected", [
    (lambda s: s["narration"].update(am=s["narration"]["am"] + " አዎ።"), [("voice", "am/s03")]),
    (lambda s: s.update(image_prompt=s["image_prompt"] + " at dawn"), [("picture", "s03_9x16")])])
def test_changing_one_line_or_picture_remakes_only_that_shot(sb, monkeypatch, tmp_path, change, expected):
    calls = []
    _stranger(sb, monkeypatch, calls)
    assert _command(monkeypatch, tmp_path, sb, "film") == 0
    calls.clear()
    change(sb["shots"][2])
    assert _command(monkeypatch, tmp_path, sb, "film") == 0
    assert calls == [*expected, ("film", "built")]


def test_the_one_command_still_waits_for_consent(sb, monkeypatch, tmp_path):
    calls = []
    _stranger(sb, monkeypatch, calls)
    sb["people"]["consent"] = "pending"
    assert _command(monkeypatch, tmp_path, sb, "film") == 1 and calls == []


def test_review_mode_and_single_stages_are_still_gated(sb, monkeypatch, tmp_path):
    calls = []
    _stranger(sb, monkeypatch, calls)
    sb["approvals"] = {}
    assert _command(monkeypatch, tmp_path, sb, "film", "--review") == 1
    assert _command(monkeypatch, tmp_path, sb, "narration") == 1 and calls == []
