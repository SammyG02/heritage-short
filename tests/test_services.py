"""Services are choices: shown with their limits, changed only by the person, and never losing finished work."""
import json

import pytest

from pipeline import gpu, keyframes, narration, qa, script, services, web
from pipeline.core import budget, cache, config, providers, runlog, settings, storyboard
from tests.test_personal_films import draft
from tests.test_review_fixes import voices, wav
from tests.conftest import BOARD


@pytest.fixture
def sb(monkeypatch, tmp_path):
    data = json.loads(BOARD.read_text(encoding="utf-8"))
    monkeypatch.setattr(config, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(services, "live", lambda fresh=False: {"gemini": None, "addis": None, "kaggle": None})
    return data


def log(**row):
    runlog.write({"ts": "2999-01-01T00:00:00+00:00", "status": "ok", "error": None, "output": None, "run_id": "r", "stage": "x", "item": "i", **row})


def group(sb, gid):
    return {o["id"]: o for o in next(g for g in services.state(sb)["groups"] if g["id"] == gid)["options"]}


def film(monkeypatch, **k):
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **kw: draft(quoted="ana"))
    return script.new("word " * 20, "am", "home", "family", "close", **k)[1]


# ---------------------------------------------------------------- limits
@pytest.mark.parametrize("error,limit", [
    ("HTTP 429: Rate limit exceeded for model m (limit: 10 requests per day on Free Tier).", 10),
    ("HTTP 429: * Quota exceeded for metric: x_requests, limit: 3, model: m, description: Generate content requests per minute limit exceeded", None),
    ("HTTP 429: * x, limit: 3, model: m, description: requests per minute exceeded * x, limit: 20, model: m, description: Generate content requests per day limit exceeded", 20),
    ("HTTP 429: * x, limit: 0, model: m, description: Generate content input tokens per minute", 0),
    ("HTTP 503: busy", None)])
def test_a_limit_is_only_what_google_has_said(error, limit):
    log(model="gemini-x", provider="gemini", status="error", error=error)
    assert budget.day_limit("gemini-x") == limit


KEYS = ("GEMINI_API_KEY", "ADDIS_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
NOW = {"gemini": None, "addis": {"balance": 400.0, "spent": 100.0, "start": 500.0, "currency": "Birr", "per_minute": 5.0}, "kaggle": {"used": 0.93, "total": 30.0, "reset": "2026-11-28T00:00:00+00:00"}}


@pytest.fixture
def ready(monkeypatch):
    for k in KEYS:
        monkeypatch.setenv(k, "fake-key-for-tests")
    monkeypatch.setattr(services, "live", lambda fresh=False: NOW)


def test_nothing_is_offered_before_it_has_worked(sb, ready):
    assert [g["id"] for g in services.state(sb)["groups"]] == ["motion"]
    assert list(group(sb, "motion")) == ["camera"]


def test_a_service_appears_once_it_has_worked(sb, ready):
    for m, p, s in (("gemini-3.8-flash-tts", "gemini", "narration"), ("addis-voices-2", "addis-ai", "smoke"), ("@cf/flux", "cloudflare", "keyframes"), ("wan", "kaggle-2xT4", "shots"), ("ace", "kaggle-2xT4", "music")):
        log(model=m, provider=p, stage=s)
    log(model="gemini-2.5-flash-preview-tts", provider="gemini", status="error", error="HTTP 429 limit: 10 requests per day")
    assert list(group(sb, "voice")) == ["addis", "gemini:gemini-3.8-flash-tts"]  # the refused model and untested OmniVoice are left out
    assert list(group(sb, "pictures")) == ["cloudflare"] and list(group(sb, "motion")) == ["clip", "camera"] and list(group(sb, "music")) == ["ace"]
    log(model="omni", provider="kaggle-2xT4", stage="narration")
    log(model="flux", provider="kaggle-2xT4", stage="keyframes")
    assert "omnivoice" in group(sb, "voice") and "kaggle" in group(sb, "pictures")


def test_everything_offered_has_a_known_limit_or_is_free(sb, ready):
    log(model="gemini-3.8-flash", provider="gemini", stage="script")  # it works, but Google has not said its limit
    log(model="gemini-3.1-flash-tts-preview", provider="gemini", stage="narration")
    offered = [o for g in services.state(sb)["groups"] for o in g["options"]]
    assert all(o["meter"] and o["meter"]["limit"] for o in offered if o["id"] != "camera")


def test_without_a_key_nothing_of_that_service_is_offered(sb, ready, monkeypatch):
    log(model="gemini-3.8-flash-tts", provider="gemini")
    monkeypatch.delenv("GEMINI_API_KEY")
    assert "voice" not in [g["id"] for g in services.state(sb)["groups"]]


def test_used_up_models_stay_and_paid_ones_go(sb, ready):
    for m in ("gemini-3.8-flash-tts", "gemini-2.5-pro-preview-tts"):
        log(model=m, provider="gemini")
    log(model="gemini-3.8-flash-tts", provider="gemini", status="error", error="HTTP 429 limit: 10 requests per day")
    log(model="gemini-2.5-pro-preview-tts", provider="gemini", status="error", error="HTTP 429 limit: 0, model: x")
    v = group(sb, "voice")
    assert list(v) == ["gemini:gemini-3.8-flash-tts"] and v["gemini:gemini-3.8-flash-tts"]["wait"]


def test_pictures_are_counted_in_pictures(sb, ready):
    log(model="@cf/flux", provider="cloudflare", list_price_usd=0.011)
    m = group(sb, "pictures")["cloudflare"]["meter"]
    assert m["unit"] == "pictures" and 0 < m["used"] < m["limit"] == 59


def test_real_balances_are_used_when_the_service_gives_them(sb, ready):
    log(model="addis-voices-2", provider="addis-ai")
    log(model="wan", provider="kaggle-2xT4", stage="shots")
    m = group(sb, "voice")["addis"]["meter"]
    assert (m["used"], m["limit"], m["unit"], m["source"]) == (100, 500, "Birr", "live")
    assert group(sb, "motion")["clip"]["meter"]["source"] == "live"


def test_groq_appears_when_its_key_is_accepted(sb, ready, monkeypatch):
    services._kept.clear()
    assert "writing" not in [g["id"] for g in services.state(sb)["groups"]]
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setattr(providers, "groq_models", lambda: ["openai/gpt-oss-120b"])
    assert list(group(sb, "writing")) == ["auto", "groq:openai/gpt-oss-120b"]
    services._kept.clear()


def test_a_service_that_does_not_answer_is_unknown_not_empty(monkeypatch):
    services._kept.clear()
    for k in ("GEMINI_API_KEY", "ADDIS_API_KEY", "KAGGLE_API_TOKEN"):
        monkeypatch.setenv(k, "k")

    def down(*a, **k):
        raise OSError
    monkeypatch.setattr(providers, "gemini_models", down)
    monkeypatch.setattr(providers, "addis_usage", down)
    monkeypatch.setattr(gpu, "kaggle", down)
    assert services.live(True) == {"gemini": None, "addis": None, "kaggle": None}


def test_kaggle_quota_is_read(monkeypatch):
    monkeypatch.setattr(gpu, "kaggle", lambda *a, **k: "resource,used,remaining,total,refreshAt\nGPU,0.93h,29.07h,30.00h,2026-11-28T00:00:00+00:00\nTPU,0.00h,20.00h,20.00h,x\n")
    assert services._kaggle() == {"used": 0.93, "total": 30.0, "reset": "2026-11-28T00:00:00+00:00"}


# ---------------------------------------------------------------- Addis AI first
def test_new_films_use_addis_when_its_key_is_there(monkeypatch):
    assert narration.engine(film(monkeypatch), "am") == "gemini"
    monkeypatch.setenv("ADDIS_API_KEY", "k")
    sb = film(monkeypatch)
    v = sb["voices"]["am"]
    assert storyboard.validate(sb) == [] and v["engine"] == "addis"
    assert v["voice"].startswith("am-") and v["characters"]["ana"]["voice"].startswith("am-") and v["voice"] != v["characters"]["ana"]["voice"]
    assert sb["voices"]["en"]["voice"].startswith("en-")


def test_a_woman_narrator_and_a_woman_quoted_do_not_share_a_voice(monkeypatch):
    monkeypatch.setenv("ADDIS_API_KEY", "k")
    v = film(monkeypatch, narrator="woman")["voices"]["am"]
    assert v["voice"] != v["characters"]["ana"]["voice"]


def test_a_true_story_does_not_go_to_addis_by_itself(monkeypatch):
    monkeypatch.setenv("ADDIS_API_KEY", "k")
    sb = film(monkeypatch, true_story=True, consent_record="My mother agreed in person to the story and the film.")
    assert narration.engine(sb, "am") == "gemini"
    with pytest.raises(web.Refused, match="may train"):
        web.set_voice(sb, {"engine": "addis", "narrator": "am-dawit", "agreed": "yes"})
    web.set_voice(sb, {"engine": "addis", "narrator": "am-dawit", "agreed": "My mother agreed in person that it may go to them."})
    assert narration.engine(sb, "am") == "addis" and storyboard.validate(sb) == []


# ---------------------------------------------------------------- switching never loses work
def test_switching_voice_service_and_back_keeps_every_recording(sb):
    voices(sb)
    old = {k: sb["voices"]["am"][k] for k in ("voice",)}
    sb["people"]["addis_consent"] = "agreed"
    chars = {"mother": sb["voices"]["am"]["characters"]["mother"]["voice"]}
    web.set_voice(sb, {"engine": "addis", "narrator": "am-dawit", "characters": {"mother": "am-sara"}})
    assert len(narration.stale(sb, "am")) == 12
    for s in sb["shots"]:
        cache.store(narration.path(sb, s, "am"), wav(1000), narration.inputs(sb, s, "am"))
    web.set_voice(sb, {"engine": "gemini", "narrator": old["voice"], "characters": chars})
    assert narration.stale(sb, "am") == []


def test_changing_the_google_model_keeps_finished_lines_and_their_approvals(sb):
    voices(sb)
    late = sb["shots"][10]
    narration.path(sb, late, "am").unlink()
    keys = {s["id"]: narration.approval_key(sb, s, "am") for s in sb["shots"]}
    v = sb["voices"]["am"]
    web.set_voice(sb, {"engine": "gemini", "model": "gemini-2.5-flash-preview-tts", "narrator": v["voice"]})
    assert [s["id"] for s in narration.stale(sb, "am")] == [late["id"]]
    assert {s["id"]: narration.approval_key(sb, s, "am") for s in sb["shots"]} == keys
    assert narration.parts(sb, late, "am")[0]["model"] == "gemini-2.5-flash-preview-tts"
    assert sb["models"]["tts_fallbacks"] == [] and storyboard.validate(sb) == []


def test_coming_back_to_google_with_another_model_still_keeps_its_old_lines(sb):
    voices(sb)
    sb["people"]["addis_consent"] = "agreed"
    v = sb["voices"]["am"]
    narrator, chars = v["voice"], {"mother": v["characters"]["mother"]["voice"]}
    web.set_voice(sb, {"engine": "addis", "narrator": "am-dawit", "characters": {"mother": "am-sara"}})
    web.set_voice(sb, {"engine": "gemini", "model": "gemini-3.8-flash-tts", "narrator": narrator, "characters": chars})
    assert narration.stale(sb, "am") == []


@pytest.mark.parametrize("model", ["gemini-3.8-flash", "../x-tts", "nano-tts"])
def test_only_google_voice_models_can_be_chosen(sb, model):
    with pytest.raises(web.Refused):
        web.set_voice(sb, {"engine": "gemini", "model": model, "narrator": "Algieba"})


def test_collected_gpu_voices_stay_out_of_the_other_services_files(sb):
    sb["voices"]["am"]["engine"] = "omnivoice"
    assert "omnivoice" in narration.part_path(sb, sb["shots"][0], "am", 1).parts
    sb["voices"]["am"]["engine"] = "gemini"
    assert narration.path(sb, sb["shots"][0], "am").parent.name == "am"


def test_picture_service_and_motion(sb):
    before = {s["id"]: cache.key(keyframes.inputs(sb, s, "9x16")) for s in sb["shots"]}
    web.set_service(sb, {"pictures": "kaggle"})
    assert keyframes.service(sb) == "kaggle"
    web.set_service(sb, {"motion": "camera"})
    assert {s["motion"] for s in sb["shots"]} == {"camera"} and storyboard.validate(sb) == []
    assert before == {s["id"]: cache.key(keyframes.inputs(sb, s, "9x16")) for s in sb["shots"]}
    for bad in ({"pictures": "grok"}, {"motion": "spin"}):
        with pytest.raises(web.Refused):
            web.set_service(sb, bad)


# ---------------------------------------------------------------- who writes and checks
def test_a_chosen_writer_is_used_alone(monkeypatch):
    asked = []

    def down(stage, item, prompt, model, **k):
        asked.append(model)
        raise providers.ProviderError("busy")
    monkeypatch.setattr(providers, "gemini_json", down)
    for choice, want in (("auto", script.MODELS), ("gemini:gemini-3.6-flash", ["gemini-3.6-flash"])):
        asked.clear()
        settings.save(writer=choice)
        with pytest.raises(providers.ProviderError):
            script._generate("p")
        assert asked == want


@pytest.mark.parametrize("bad", ["", "None", "groq:other", "gemini:gemini-3.8-flash-tts", "gemini:../x", "gemini:gemini-nano-banana-2.1"])
def test_unknown_writers_are_refused(bad):
    with pytest.raises(config.PipelineError):
        services.check_writer(bad)


def test_groq_answers_and_its_limit_is_remembered(monkeypatch):
    sent = {}

    class R:
        ok = True
        headers = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "993"}

        def json(self):
            return {"choices": [{"message": {"content": '{"a": 1}'}}], "usage": {"prompt_tokens": 1, "completion_tokens": 2}}

    def post(url, headers, json, timeout):
        sent.update(url=url, **json)
        return R()
    monkeypatch.setenv("GROQ_API_KEY", "secret-key-value")
    monkeypatch.setattr(providers.requests, "post", post)
    assert providers.groq_json("script", "s", "p", "openai/gpt-oss-120b") == {"a": 1}
    assert sent["url"].startswith("https://api.groq.com/") and sent["response_format"] == {"type": "json_object"}
    assert budget.groq_limits() == {"openai/gpt-oss-120b": {"limit": 1000, "left": 993}}
    assert "secret-key-value" not in config.RUNS.read_text(encoding="utf-8")


def test_groq_checks_pictures_only_when_it_can_see_them_all(sb, monkeypatch, tmp_path):
    ref = tmp_path / "r.png"
    ref.write_bytes(b"x")
    seen = []
    monkeypatch.setattr(providers, "groq_json", lambda stage, item, p, model, t, images: seen.append(len(images)) or {k: 9 for k in qa.KEYS})
    settings.save(writer="groq:openai/gpt-oss-120b")
    assert qa.check(sb, sb["shots"][0], "9x16", b"x", [ref]) is None
    settings.save(writer="groq:" + qa.GROQ_SEES)
    assert qa.check(sb, sb["shots"][0], "9x16", b"x", [ref, ref, ref]) is None and seen == []
    assert qa.check(sb, sb["shots"][0], "9x16", b"x", [ref, ref])["worst"] == 9 and seen == [3]
    monkeypatch.setattr(providers, "groq_json", lambda *a: config.secret("GROQ_API_KEY"))  # no key: unchecked, not a crash
    assert qa.check(sb, sb["shots"][0], "9x16", b"x", [ref]) is None


def test_settings_survive_a_broken_file():
    settings.save(writer="auto")
    settings.file().write_text("[]", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS


def test_addis_gets_one_request_id_for_all_tries_of_a_line(monkeypatch):
    sent = []

    class Busy:
        ok, status_code, text = False, 503, "busy"

    def post(url, headers, timeout, json):
        sent.append(json["client_request_id"])
        return Busy()
    monkeypatch.setenv("ADDIS_API_KEY", "k")
    monkeypatch.setattr(providers.requests, "post", post)
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    for _ in range(2):
        with pytest.raises(providers.ProviderError):
            providers.addis_tts("narration", "am/s01", "x", "v", "am")
    assert len(sent) == 6 and len(set(sent)) == 2 and all(sent)


@pytest.mark.parametrize("link,ok", [("https://cdn.addisassistant.com/a.mp3", True), ("http://cdn.addisassistant.com/a.mp3", False), ("https://evil.example/a.mp3", False),
                                     ("https://evil-addisassistant.com/a.mp3", False), ("https://cdn.addisassistant.com@evil.example/a.mp3", False), ("", False)])
def test_voice_samples_come_only_from_addis_and_never_get_the_key(monkeypatch, link, ok):
    asked = []

    class Got:
        ok, is_redirect, content = True, False, b"ID3 sound"

    def get(url, **k):
        asked.append((url, k))
        return Got()
    providers._samples.clear()
    monkeypatch.setattr(providers, "addis_voices", lambda lang: [{"id": "am-x", "sample": link}])
    monkeypatch.setattr(providers.requests, "get", get)
    if ok:
        assert providers.addis_sample("am", "am-x") == (b"ID3 sound", "audio/mpeg")
        providers.addis_sample("am", "am-x")
        assert len(asked) == 1 and "headers" not in asked[0][1]
    else:
        with pytest.raises(providers.ProviderError):
            providers.addis_sample("am", "am-x")
        assert asked == []
    providers._samples.clear()
