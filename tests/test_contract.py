"""Offline tests: the contract, the cache and the dependency rules. No network or keys."""
import copy
import json

import pytest

from pipeline import assemble, gpu, keyframes, narration, qa, script, shots
from pipeline.core import approvals, budget, cache, config, providers, runlog, storyboard
from tests.conftest import BOARD


@pytest.fixture
def sb():
    return json.loads(BOARD.read_text(encoding="utf-8"))


def test_storyboard_is_valid(sb):
    assert storyboard.validate(sb) == []
    assert storyboard.validate(json.loads((config.ROOT / "storyboard.json").read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("change", [
    lambda s: s["shots"][0].pop("reason"),
    lambda s: s["shots"][1].update(id="s01"),
    lambda s: s["shots"][0]["narration"].pop("en"),
    lambda s: s["shots"][0].update(references=["nobody"]),
    lambda s: s.update(shots=s["shots"][:5]),
    lambda s: s["people"].update(real_people=True),
    lambda s: s["end_card"].update(lines=["The end"]),
    lambda s: [x.update(duration_s=12) for x in s["shots"]],
    lambda s: s["music"].update(chosen_seed=999),
])
def test_bad_storyboards_are_rejected(sb, change):
    change(sb)
    assert storyboard.validate(sb)


def test_narration_edit_touches_only_that_line(sb):
    new = copy.deepcopy(sb)
    new["shots"][2]["narration"]["am"] += " አዎ።"
    for a, b in zip(sb["shots"], new["shots"]):
        same_voice = cache.key(narration.inputs(sb, a, "am")) == cache.key(narration.inputs(new, b, "am"))
        assert same_voice == (a["id"] != "s03")
        assert cache.key(narration.inputs(sb, a, "en")) == cache.key(narration.inputs(new, b, "en"))
        assert cache.key(keyframes.inputs(sb, a, "9x16")) == cache.key(keyframes.inputs(new, b, "9x16"))


def test_image_edit_touches_only_that_shot(sb):
    new = copy.deepcopy(sb)
    new["shots"][4]["image_prompt"] = "a different cup"
    changed = [a["id"] for a, b in zip(sb["shots"], new["shots"])
               if cache.key(keyframes.inputs(sb, a, "9x16")) != cache.key(keyframes.inputs(new, b, "9x16"))]
    assert changed == ["s05"]


def test_cache_detects_changed_inputs_and_altered_files(tmp_path):
    p = tmp_path / "a.bin"
    cache.store(p, b"one", {"x": 1})
    assert cache.fresh(p, {"x": 1})
    assert not cache.fresh(p, {"x": 2})
    p.write_bytes(b"tampered")
    assert not cache.fresh(p, {"x": 1})


def test_retry_stops_after_three_and_not_on_client_errors(monkeypatch):
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    calls = []

    def flaky(attempt):
        calls.append(attempt)
        raise providers.ProviderError("busy", retryable=True)
    with pytest.raises(providers.ProviderError):
        providers.retry(flaky)
    assert calls == [1, 2, 3]
    calls.clear()

    def bad(attempt):
        calls.append(attempt)
        raise providers.ProviderError("bad request")
    with pytest.raises(providers.ProviderError):
        providers.retry(bad)
    assert calls == [1]


def test_log_records_failures_and_hides_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    with pytest.raises(ValueError):
        with runlog.call("t", "i", "p", "m", {}):
            raise ValueError("failed with super-secret-value")
    text = (tmp_path / "runs.jsonl").read_text(encoding="utf-8")
    assert json.loads(text)["status"] == "error"
    assert "super-secret-value" not in text


def test_network_error_is_not_a_failed_job():
    assert gpu.parse_status('x has status "KernelWorkerStatus.QUEUED"') == "queued"
    assert gpu.parse_status('x has status "KernelWorkerStatus.ERROR"') == "error"
    assert gpu.parse_status("ConnectionError: Max retries exceeded") == "unknown"


def test_true_story_is_locked_until_consent_is_recorded(sb, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    for name in ("gemini_tts", "flux", "gemini_json"):
        monkeypatch.setattr(providers, name, lambda *a, **k: calls.append(a) or b"x")
    sb["people"].update(based_on_real_people=True, consent="pending")
    for stage in (lambda: narration.run(sb, "am"), lambda: keyframes.run_references(sb), lambda: keyframes.run(sb),
                  lambda: gpu.submit_wan(sb), lambda: gpu.submit_music(sb)):
        with pytest.raises(config.PipelineError, match="consent"):
            stage()
    assert calls == []
    sb["people"]["consent"] = "recorded"
    storyboard.require_consent(sb)


def test_quoted_words_use_the_character_voice_and_retake_alone(sb, monkeypatch, tmp_path):
    import io
    import wave
    said = []

    def speak(stage, item, text, voice, style, model):
        said.append((text, voice))
        raw = io.BytesIO()
        with wave.open(raw, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x10\x10" * 2400)
        return raw.getvalue()
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    monkeypatch.setattr(providers, "gemini_tts", speak)
    sb["people"]["consent"] = "recorded"
    sb["voices"] = {"en": {"voice": "Man", "style": "a", "characters": {"mother": {"voice": "Woman", "style": "b"}}}}
    monkeypatch.setattr(narration, "one_call", lambda *a: False)
    sb["shots"] = [dict(sb["shots"][0], quote_voice="mother", narration={"en": "She says: “Nine years.”"})]
    sb.pop("approvals")
    monkeypatch.setattr(narration, "estimate_s", lambda *a: 75)
    narration.run(sb, "en")
    assert said == [("She says:", "Man"), ("Nine years.", "Woman")]
    assert narration.seconds(narration.path(sb, sb["shots"][0], "en")) == pytest.approx(0.4)
    sb["shots"][0]["narration"]["en"] = "She says: “Nine long years.”"
    narration.run(sb, "en")
    assert said[2:] == [("Nine long years.", "Woman")]


def _png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, "PNG")
    return buf.getvalue()


def test_locked_look_and_emotion_reach_every_prompt(sb):
    for s in sb["shots"]:
        text = keyframes.prompt(sb, s, "9x16")
        assert s["emotion"] in text and s["emotion"] in shots.motion(s)
        for name in s["references"]:
            assert sb["references"][name]["look"] in text


def test_changing_the_chosen_mother_makes_every_shot_of_her_stale(sb, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    for seed in (11, 22):
        cache.store(keyframes.ref_path(sb, "mother", seed), bytes([seed]), {})
    sb["references"]["mother"]["chosen_seed"] = 11
    before = {s["id"]: cache.key(keyframes.inputs(sb, s, "9x16")) for s in sb["shots"]}
    sb["references"]["mother"]["chosen_seed"] = 22
    changed = {s["id"] for s in sb["shots"] if cache.key(keyframes.inputs(sb, s, "9x16")) != before[s["id"]]}
    assert changed == {s["id"] for s in sb["shots"] if "mother" in s["references"]}


def test_a_bad_picture_is_redrawn_and_the_best_is_kept(sb, monkeypatch):
    drawn, worst = [], iter([3, 9])
    monkeypatch.setattr(providers, "flux", lambda *a, **k: drawn.append(a[5]) or _png())
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: {**dict.fromkeys(qa.KEYS, 10), "identity": next(worst), "problem": "face"})
    s = sb["shots"][1]
    _, report = qa.best_of(sb, s, "9x16", keyframes.inputs(sb, s, "9x16"), [config.FONT])
    assert drawn == [s["seed"], s["seed"] + qa.SEED_STEP]
    assert report["status"] == "passed" and report["seed_used"] == drawn[1]


def test_no_checker_means_unchecked_not_passed(sb, monkeypatch):
    def down(*a, **k):
        raise providers.ProviderError("quota")
    monkeypatch.setattr(providers, "flux", lambda *a, **k: _png())
    monkeypatch.setattr(providers, "gemini_json", down)
    s = sb["shots"][1]
    assert qa.best_of(sb, s, "9x16", keyframes.inputs(sb, s, "9x16"), [])[1]["status"] == "unchecked"


def test_voice_falls_back_keeps_the_voice_and_records_the_model(sb, monkeypatch, tmp_path):
    asked = []

    def speak(stage, item, text, voice, style, model):
        asked.append((voice, model))
        if model == "first":
            raise providers.ProviderError("quota")
        return b"x"
    monkeypatch.setattr(providers, "gemini_tts", speak)
    sb["models"]["tts_fallbacks"] = ["second", "third"]
    assert narration._speak(sb, "am/s01", {"text": "t", "voice": "V", "style": "s", "model": "first"}) == (b"x", "second")
    assert asked == [("V", "first"), ("V", "second")]


def test_drafts_without_emotion_look_or_transition_are_rejected(sb):
    assert script.lint(sb) == []
    sb["shots"][0].pop("emotion")
    sb["references"]["mother"].pop("look")
    assert len(script.lint(sb)) == 2


def _log(*rows):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    config.RUNS.write_text("".join(json.dumps({"ts": now, "run_id": "r", "stage": "x", "item": str(i), "provider": "p", "status": "ok", "error": None, **r}) + "\n" for i, r in enumerate(rows)), encoding="utf-8")


def _lines(monkeypatch, seconds):
    monkeypatch.setattr(narration, "speech", lambda p: (0.0, seconds))


@pytest.mark.parametrize("seconds", [2.0, 3.0, 4.5, 6.0, 6.8, 7.1])
def test_film_is_always_60_to_90_seconds(sb, monkeypatch, seconds):
    _lines(monkeypatch, seconds)
    for s in sb["shots"]:
        s["duration_s"] = 2
    rows, total = assemble.timeline(sb, "am")
    assert 60 <= total <= 90
    assert abs(sum(r["frames"] for r in rows) / 24 + sb["end_card"]["duration_s"] - total) < 1e-6
    for r in rows:
        assert r["frames"] / 24 >= assemble.LEAD + r["voice"]


def test_film_that_cannot_fit_is_refused(sb, monkeypatch):
    _lines(monkeypatch, 9.0)
    with pytest.raises(config.PipelineError, match="cannot be fitted"):
        assemble.check_length(assemble.timeline(sb, "am")[1])


def test_voice_never_starts_a_job_it_cannot_finish(sb, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    monkeypatch.setattr(providers, "gemini_tts", lambda *a: pytest.fail("called a model"))
    sb["models"]["tts_fallbacks"] = []
    sb["voices"]["am"]["model"] = "m-tts"
    for s in sb["shots"]:
        s.pop("tts_model", None)
    monkeypatch.setattr(narration, "estimate_s", lambda *a: 80)
    sb["shots"][2]["quote_voice"] = "uncle"
    sb["shots"][2]["narration"]["am"] = "አለ፦ «ጠበቁ።»"
    sb["voices"]["am"]["characters"]["uncle"] = {"voice": "Third", "style": "x"}
    sb.pop("approvals")
    with pytest.raises(config.PipelineError, match="15 needed, 10 left"):
        narration.run(sb, "am")


def test_voice_uses_one_model_for_the_job_when_one_has_room(sb):
    sb["models"]["tts_fallbacks"] = ["b-tts"]
    _log(*[{"model": "a-tts"}] * 8)
    assert narration._order(sb, "a-tts", 5) == ["b-tts", "a-tts"]
    assert narration._order(sb, "a-tts", 2) == ["a-tts", "b-tts"]
    _log({"model": "a-tts", "status": "error", "error": "limit: 10 requests per day"})
    assert budget.tts_left("a-tts") == 0


@pytest.mark.parametrize("text", ["4 አመት", "አንድ % ነው", "ነበሩ። ፤ ልጅ", "እሱ said", "«ሌላ የት"])
def test_unreadable_lines_are_found_before_a_voice_call(sb, text):
    assert narration.text_problems(sb, "am") == []
    sb["shots"][0]["narration"]["am"] = text
    assert narration.text_problems(sb, "am")


def test_order_is_script_then_voice_then_picture(sb, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    monkeypatch.setattr(providers, "flux", lambda *a, **k: pytest.fail("drew a picture"))
    monkeypatch.setattr(providers, "gemini_tts", lambda *a: pytest.fail("made a voice"))
    monkeypatch.setattr(narration, "estimate_s", lambda *a: 80)
    sb["people"]["consent"], sb["approvals"] = "recorded", {}
    with pytest.raises(config.PipelineError, match="approve the script"):
        narration.run(sb, "am", only=["s01"])
    keyframes.run(sb, only=["s01"])
    assert shots.plan(sb)[0] == []
    s = sb["shots"][0]
    approvals.give(sb, "script", "s01", approvals.script_key(s))
    assert approvals.ok(sb, "script", "s01", approvals.script_key(s))
    s["narration"]["am"] += " አዎ"
    assert not approvals.ok(sb, "script", "s01", approvals.script_key(s))


def test_motion_stays_inside_the_hours_and_takes_speaking_faces_first(sb, monkeypatch):
    monkeypatch.setattr(shots, "has_wan", lambda *a: False)
    monkeypatch.setattr(cache, "fresh", lambda *a: True)
    monkeypatch.setattr(type(config.ROOT), "exists", lambda self: True)
    monkeypatch.setattr(cache, "file_sha", lambda p: "x")
    monkeypatch.setattr(budget, "rows", lambda: [])
    sb.pop("approvals")
    chosen, left_out, _, hours = shots.plan(sb, hours=1)
    assert [(s["id"], r) for s, r in chosen] == [("s05", "9x16"), ("s09", "9x16")] and hours <= 1 and left_out
    assert not {"s04", "s07", "s10", "s12"} & {s["id"] for s, _ in chosen + left_out}
    monkeypatch.setattr(budget, "gpu_left_h", lambda: 2.0)
    assert shots.plan(sb)[0] == []


def test_redraws_are_capped(sb, monkeypatch):
    drawn = []
    monkeypatch.setattr(providers, "flux", lambda *a, **k: drawn.append(1) or _png())
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **k: {**dict.fromkeys(qa.KEYS, 2), "problem": "bad"})
    s, extra = sb["shots"][1], [1]
    for _ in range(3):
        qa.best_of(sb, s, "9x16", keyframes.inputs(sb, s, "9x16"), [config.FONT], extra)
    assert len(drawn) == 4


def test_new_films_fit_one_day_of_voice_and_use_every_character(sb):
    sb["shots"][0].pop("tts_model")
    assert not any("voice calls" in x for x in script.limits(sb))
    for s, who in zip(sb["shots"], ("uncle", "aunt", "child") * 4):
        s["quote_voice"], s["narration"]["am"] = who, "አለ፦ «ጠበቁ።»"
    sb["voices"]["am"]["characters"] = {n: {"voice": n, "style": "x"} for n in ("uncle", "aunt", "child")}
    assert any("voice calls" in x for x in script.limits(sb))
    sb["references"]["uncle"] = dict(sb["references"]["mother"])
    assert any("uncle" in x for x in script.lint(sb))


def _tone(seconds, rate=24000, level=6000):
    import array
    return array.array("h", [level if (i // 40) % 2 else -level for i in range(int(seconds * rate))])


def _take(lengths, pauses, rate=24000):
    from pipeline import voice_take
    x = _tone(lengths[0])
    for s, p in zip(lengths[1:], pauses):
        x.extend([0] * int(p * rate))
        x.extend(_tone(s))
    return voice_take.write(x, rate)


def test_one_recording_is_cut_into_the_right_lines():
    from pipeline import voice_take
    wav = _take([2, 1, 3], [1.5, 1.6])
    got = voice_take.split(wav, ["a" * 20, "b" * 10, "c" * 30])
    assert [round(len(voice_take.read(g)[0]) / 24000, 1) for g in got] == [2.1, 1.2, 3.1]


@pytest.mark.parametrize("pauses", [[0.8, 0.8], [1.5], [1.5, 0.3]])
def test_an_unsafe_cut_is_refused(pauses):
    from pipeline import voice_take
    lengths = [2, 2, 2][:len(pauses) + 1]
    with pytest.raises(config.PipelineError):
        voice_take.split(_take(lengths, pauses), ["a" * 20, "b" * 20] if pauses == [0.8, 0.8] else ["a" * 20] * 3)


def _ready(sb, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "OUTPUTS", tmp_path)
    monkeypatch.setattr(narration, "estimate_s", lambda *a: 80)
    for s in sb["shots"]:
        s.pop("tts_model", None)


def test_the_whole_script_takes_one_call(sb, monkeypatch, tmp_path):
    _ready(sb, monkeypatch, tmp_path)
    calls = []

    def recording(stage, item, turns, voices, model):
        calls.append((len(turns), sorted(voices)))
        return _take([len(s["narration"]["am"]) / 14 for s in sb["shots"]], [1.6] * 11)
    monkeypatch.setattr(providers, "gemini_take", recording)
    monkeypatch.setattr(providers, "gemini_tts", lambda *a: pytest.fail("a second call"))
    narration.run(sb, "am")
    assert calls == [(14, ["Mother", "Narrator"])]
    assert not narration.stale(sb, "am")
    assert len(list((tmp_path / "one-percent/narration/am/takes").glob("*.wav"))) == 1


def test_a_recording_that_cannot_be_cut_is_kept_and_smaller_ones_tried(sb, monkeypatch, tmp_path):
    _ready(sb, monkeypatch, tmp_path)
    calls = []

    def recording(stage, item, turns, voices, model):
        calls.append(item)
        texts = sb["shots"] if item == "am/s01-s12" else sb["shots"][:6] if item == "am/s01-s06" else sb["shots"][6:]
        return _take([len(s["narration"]["am"]) / 14 for s in texts], [0.4 if item == "am/s01-s12" else 1.6] * (len(texts) - 1))
    monkeypatch.setattr(providers, "gemini_take", recording)
    monkeypatch.setattr(providers, "gemini_tts", lambda *a: pytest.fail("line by line"))
    narration.run(sb, "am")
    assert calls == ["am/s01-s12", "am/s01-s06", "am/s07-s12"] and not narration.stale(sb, "am")


def test_addis_is_chosen_never_automatic_and_makes_every_line_again(sb, monkeypatch, tmp_path):
    _ready(sb, monkeypatch, tmp_path)
    before = {s["id"]: cache.key(narration.inputs(sb, s, "am")) for s in sb["shots"]}
    asked = []
    monkeypatch.setattr(providers, "addis_tts", lambda stage, item, text, voice, lang: asked.append(voice) or _take([1], []))
    monkeypatch.setattr(providers, "gemini_take", lambda *a: (_ for _ in ()).throw(providers.ProviderError("quota")))
    monkeypatch.setattr(providers, "gemini_tts", lambda *a: (_ for _ in ()).throw(providers.ProviderError("quota")))
    sb["models"]["tts_fallbacks"] = ["b-tts"]
    with pytest.raises(config.PipelineError):
        narration.run(sb, "am")
    assert asked == []
    sb["voices"]["am"].update(engine="addis", voice="am-yohannes")
    sb["voices"]["am"]["characters"]["mother"]["voice"] = "am-hamen"
    with pytest.raises(config.PipelineError, match="may train"):  # a true story needs its own yes
        narration.run(sb, "am")
    assert asked == []
    sb["people"]["addis_consent"] = "The people in it agreed in person that it may go there."
    assert all(cache.key(narration.inputs(sb, s, "am")) != before[s["id"]] for s in sb["shots"])
    narration.run(sb, "am")
    assert len(asked) == 14 and set(asked) == {"am-yohannes", "am-hamen"}


def test_addis_audio_comes_back_as_plain_wav(monkeypatch):
    import base64
    import io
    import wave
    raw = io.BytesIO()
    with wave.open(raw, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x01\x00" * 44100)

    class R:
        ok = True

        def json(self):
            return {"data": {"audio": "data:audio/wav;base64," + base64.b64encode(raw.getvalue()).decode()}}
    monkeypatch.setenv("ADDIS_API_KEY", "k")
    monkeypatch.setattr(providers.requests, "post", lambda *a, **k: R())
    with wave.open(io.BytesIO(providers.addis_tts("narration", "am/s01", "ሰላም", "v", "am"))) as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (1, 24000, 2)


def test_omnivoice_only_runs_when_chosen(sb):
    with pytest.raises(config.PipelineError, match="does not use OmniVoice"):
        gpu.submit_voice(sb, "am")
    sb["voices"]["am"]["engine"] = "omnivoice"
    with pytest.raises(config.PipelineError):
        narration.run(sb, "am")
