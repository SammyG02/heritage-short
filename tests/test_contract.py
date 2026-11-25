"""Offline tests: the contract, the cache and the dependency rules. No network or keys."""
import copy
import json

import pytest

from pipeline import gpu, keyframes, narration
from pipeline.core import cache, config, providers, runlog, storyboard


@pytest.fixture
def sb():
    return json.loads((config.ROOT / "storyboard.json").read_text(encoding="utf-8"))


def test_storyboard_is_valid(sb):
    assert storyboard.validate(sb) == []


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
    for name in ("gemini_tts", "flux"):
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
    sb["shots"] = [dict(sb["shots"][0], quote_voice="mother", narration={"en": "She says: “Nine years.”"})]
    narration.run(sb, "en")
    assert said == [("She says:", "Man"), ("Nine years.", "Woman")]
    assert narration.seconds(narration.path(sb, sb["shots"][0], "en")) == pytest.approx(0.4)
    sb["shots"][0]["narration"]["en"] = "She says: “Nine long years.”"
    narration.run(sb, "en")
    assert said[2:] == [("Nine long years.", "Woman")]
