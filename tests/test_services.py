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
    runlog.write({"ts": "2999-01-01T00:00:00+00:00", "status": "ok", "error": None, "output": None, "run_id": "r", "stage": "x", "item": "i",
                  **({"account": runlog.account(row.get("provider"))} if runlog.account(row.get("provider")) else {}), **row})


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
    assert all(o["meter"] and o["meter"]["limit"] for o in offered if o["id"] != "camera" and not o.get("paid"))
    assert all("$" in o["note"] for o in offered if o.get("paid"))  # a paid service always says its price


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


def test_blocked_picture_tries_another_seed(monkeypatch):
    from types import SimpleNamespace
    from pipeline import keyframes
    from pipeline.core import providers
    bad = SimpleNamespace(ok=False, status_code=400, text='{"errors":[{"message":"AiError: Your output has been flagged.","code":3030}]}')
    with pytest.raises(providers.Flagged):
        providers._check(bad)
    tried = []

    def draw(seed):
        tried.append(seed)
        if len(tried) < 2:
            raise providers.Flagged("blocked")
        return b"png"
    assert keyframes.flagged_retry(draw, 22) == (b"png", 22 + keyframes.FLAG_STEP)
    assert tried == [22, 22 + keyframes.FLAG_STEP]

    def never(seed):
        raise providers.Flagged("blocked")
    with pytest.raises(providers.ProviderError, match="Change a few words"):
        keyframes.flagged_retry(never, 22)


def test_pictures_count_the_last_24_hours(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from pipeline.core import budget
    now = datetime.now(timezone.utc)
    row = lambda h, status="ok", error=None, usd=0.011: {"ts": (now - timedelta(hours=h)).isoformat(), "provider": "cloudflare",
                                                           "model": "@cf/black-forest-labs/flux-2-klein-4b", "status": status,
                                                           "error": error, "list_price_usd": usd if status == "ok" else 0}
    # 11 big batches 20 hours ago fill the day; midnight UTC does not empty it
    rows = [row(20) for _ in range(11)]
    monkeypatch.setattr(budget, "rows", lambda: rows)
    assert budget.flux_left() == 0
    assert timedelta(hours=3) < budget.flux_reset() - now < timedelta(hours=5)
    # Cloudflare refused although our count shows room: believe Cloudflare
    rows[:] = [row(20, usd=0.001), row(1, "error", "HTTP 429: you have used up your daily free allocation")]
    assert budget.flux_left() == 0
    rows.append(row(0.5))
    assert budget.flux_left() > 0


def test_a_new_account_starts_with_its_full_limit(monkeypatch):
    from datetime import datetime, timezone
    from pipeline.core import budget, runlog
    old = {"ts": datetime.now(timezone.utc).isoformat(), "provider": "cloudflare", "model": "@cf/black-forest-labs/flux-2-klein-4b",
           "status": "ok", "error": None, "list_price_usd": 0.2}
    monkeypatch.setattr(budget, "rows", lambda: [old])
    assert budget.flux_left() == 0                      # no account in .env: every row counts
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "new-account-for-tests")
    assert budget.flux_left() == budget.FLUX_PER_DAY    # the old rows were another account's
    with runlog.call("t", "x", "cloudflare", "m", {}) as rec:
        pass
    assert rec["account"] == runlog.account("cloudflare") and "new-account" not in str(rec)


def test_the_picture_reset_is_always_ahead(monkeypatch):
    from datetime import datetime, timezone
    from pipeline.core import budget
    monkeypatch.setattr(budget, "rows", lambda: [])
    assert budget.flux_reset() > datetime.now(timezone.utc)   # room now: the page must not see a reset that has passed


def test_the_voice_can_change_while_pictures_are_drawn(monkeypatch):
    from pipeline import web
    monkeypatch.setattr(web, "running", lambda: True)
    monkeypatch.setitem(web.job, "film", "f")
    seen = []
    monkeypatch.setattr(web, "open_board", lambda fid: seen.append(fid) or (_ for _ in ()).throw(RuntimeError("reached the edit")))
    monkeypatch.setitem(web.job, "action", "pictures")
    with pytest.raises(RuntimeError, match="reached the edit"):
        web.edit("f", {"voice": {"engine": "gemini"}})
    with pytest.raises(web.Refused):
        web.edit("f", {"voice": {"engine": "gemini"}, "shots": {}})   # anything more waits
    monkeypatch.setitem(web.job, "action", "voice")
    with pytest.raises(web.Refused):
        web.edit("f", {"voice": {"engine": "gemini"}})               # a voice job is using it


def test_wavespeed_makes_one_paid_clip_per_approved_picture_and_keeps_the_old_one(sb, monkeypatch):
    from types import SimpleNamespace
    from pipeline import keyframes, shots, wavespeed
    from pipeline.core import approvals, cache
    monkeypatch.setenv("WAVESPEED_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(wavespeed, "POLL_S", 0)
    s = sb["shots"][0]
    for x in sb["shots"]:
        x["motion"] = "camera"
    s["motion"], s["animate"] = "clip", "wavespeed"
    p = keyframes.path(sb, s, "9x16")
    cache.store(p, b"png", keyframes.inputs(sb, s, "9x16"))
    approvals.give(sb, "picture", p.stem, cache.file_sha(p))
    calls = []
    ok = lambda body: SimpleNamespace(ok=True, status_code=200, json=lambda: body, content=b"mp4", raise_for_status=lambda: None)  # noqa: E731

    def post(u, **k):
        calls.append(("post", u.split("/api/v3/")[1]))
        if u.endswith("/media/uploads"):
            return ok({"data": {"download_url": "https://x/frame.png", "upload": {"url": "https://signed", "headers": {}}}})
        assert k["json"]["duration"] in (5, 8) and k["json"]["image"] == "https://x/frame.png"
        return ok({"data": {"id": "p1"}})

    def get(u, **k):
        calls.append(("get", u))
        return ok({"data": {"status": "completed", "outputs": ["https://x/clip.mp4"]}})
    monkeypatch.setattr(wavespeed.requests, "post", post)
    monkeypatch.setattr(wavespeed.requests, "put", lambda u, **k: SimpleNamespace(status_code=200))
    monkeypatch.setattr(wavespeed.requests, "get", get)
    monkeypatch.setattr(shots, "seconds_of", lambda p: 8.1)
    wavespeed.run(sb)
    assert [c for c in calls if c[0] == "post"] == [("post", "media/uploads"), ("post", shots.WAVESPEED["fast"][0])]  # Fast by default, one paid submit
    assert shots.has_wan(sb, s, "9x16") and cache.read_meta(shots.wan_path(sb, s, "9x16"))["seconds"] == 8.1
    calls.clear()
    wavespeed.run(sb)
    assert [c for c in calls if c[0] == "post"] == []   # made: nothing is paid twice (a balance check is free)
    s.setdefault("takes", {})["clip"] = 1                 # Animate again
    assert not shots.has_wan(sb, s, "9x16") and keyframes.cache.fresh(p, keyframes.inputs(sb, s, "9x16"))  # the picture stays
    wavespeed.run(sb)
    assert (shots.wan_path(sb, s, "9x16").parent / "versions" / "s01_9x16_1.mp4").exists()   # the old clip is kept


def test_short_shots_get_5_second_clips_at_the_measured_price(sb):
    from pipeline import shots
    s = sb["shots"][0]
    s["duration_s"] = 4
    assert shots.wave_seconds(sb, s) == 5 and shots.wave_price(sb, s, "fast") == 0.10 and shots.wave_price(sb, s, "standard") == 0.15  # Fast as charged, 26 Nov
    s["duration_s"] = 9
    assert shots.wave_seconds(sb, s) == 8 and shots.wave_price(sb, s, "fast") == 0.16


def test_a_kaggle_clip_still_counts_after_switching_to_wavespeed(sb):
    from pipeline import shots
    from pipeline.core import cache
    s = sb["shots"][0]
    cache.store(shots.wan_path(sb, s, "9x16"), b"mp4", shots.wan_inputs(sb, s, "9x16", "kaggle"))
    sb["services"] = {"animate": "wavespeed"}
    assert shots.has_wan(sb, s, "9x16")


def test_wavespeed_never_passes_its_budget(sb, monkeypatch):
    from pipeline import web, wavespeed
    from pipeline.core import budget
    monkeypatch.setenv("WAVESPEED_API_KEY", "fake-key-for-tests")
    with pytest.raises(web.Refused):
        web.set_service(sb, {"motion": "wavespeed"})              # chosen shot by shot, never for the whole film
    for s in sb["shots"][:3]:
        s["motion"], s["animate"] = "clip", "wavespeed"
    monkeypatch.setattr(budget, "wavespeed_left", lambda: 0.03)    # less than one clip
    monkeypatch.setattr(wavespeed, "todo", lambda *a: [(sb["shots"][0], "9x16")])
    with pytest.raises(config.PipelineError, match="not enough for one more clip"):
        wavespeed.run(sb)


def test_a_5_second_clip_is_stretched_before_8_seconds_are_bought(sb):
    from pipeline import shots
    s = sb["shots"][0]
    s["references"], s["duration_s"] = ["mother"], 6.2
    assert shots.wave_seconds(sb, s) == 5          # 1.24x on people
    s["duration_s"] = 6.4
    assert shots.wave_seconds(sb, s) == 8          # 1.28x would show
    s["references"], s["duration_s"] = [], 7.9
    assert shots.wave_seconds(sb, s) == 5          # 1.58x on a landscape


def test_the_real_balance_wins_when_it_is_lower(monkeypatch):
    from types import SimpleNamespace
    from pipeline import wavespeed
    from pipeline.core import budget
    monkeypatch.setenv("WAVESPEED_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(budget, "wavespeed_left", lambda: 1.0)
    monkeypatch.setattr(wavespeed.requests, "get", lambda u, **k: SimpleNamespace(ok=True, json=lambda: {"code": 200, "data": {"balance": 0.42}}))
    assert wavespeed.left(fresh=True) == 0.42
    monkeypatch.setattr(wavespeed.requests, "get", lambda u, **k: SimpleNamespace(ok=False, json=lambda: {}))
    assert wavespeed.left(fresh=True) == 1.0        # no answer: the budget still applies


def test_an_unticked_service_is_never_called_for_a_true_story(sb):
    from pipeline import wavespeed
    from pipeline.core import storyboard
    sb["people"].update(based_on_real_people=True, consent="recorded")
    assert storyboard.allowed(sb, "wavespeed")                          # not answered yet: the general consent applies
    sb["people"]["ai_services"] = {"google": True, "wavespeed": False}
    with pytest.raises(config.PipelineError, match="not agreed to WaveSpeed"):
        wavespeed.run(sb)
    assert storyboard.allowed(sb, "google") and not storyboard.allowed(sb, "cloudflare")
    sb["people"]["based_on_real_people"] = False
    assert storyboard.allowed(sb, "cloudflare")                         # invented stories are not limited


def test_a_new_true_story_asks_each_person_and_each_service_before_sending_anything(monkeypatch):
    sent = []
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **kw: sent.append(1) or draft(quoted="ana"))
    mother = {"role": "mother", "story": True, "likeness": True, "words": False, "how": "in person, 26 November"}
    with pytest.raises(config.PipelineError, match="Tick it only if they agreed"):
        script.new("word " * 20, "am", "home", "family", "close", true_story=True, people_agreed=[mother], ai_services={"cloudflare": True})
    with pytest.raises(config.PipelineError, match="when and how"):
        script.new("word " * 20, "am", "home", "family", "close", true_story=True, people_agreed=[{**mother, "how": "yes"}], ai_services={"google": True})
    assert sent == []                                   # the story went nowhere
    sb = script.new("word " * 20, "am", "home", "family", "close", true_story=True, people_agreed=[mother], ai_services={"google": True, "cloudflare": True})[1]
    p = sb["people"]
    assert p["people_agreed"][0]["role"] == "mother" and p["ai_services"] == {"google": True, "cloudflare": True}
    assert "Mother: agreed to their story told, drawn as a character; in person, 26 November." in p["consent_record"]
    assert not storyboard.validate(sb) and not storyboard.allowed(sb, "wavespeed")


def test_kaggle_tries_again_when_the_connection_times_out(monkeypatch):
    from types import SimpleNamespace
    calls = []

    def run(*a, **k):
        calls.append(1)
        out = "Request failed: Connection to api.kaggle.com timed out." if len(calls) < 2 else "Kernel version 3 successfully pushed."
        return SimpleNamespace(returncode=0, stdout=out, stderr="")
    monkeypatch.setattr(gpu.subprocess, "run", run)
    monkeypatch.setattr(gpu.time, "sleep", lambda s: None)
    assert "successfully" in gpu.kaggle("kernels", "push") and len(calls) == 2
    calls.clear()
    monkeypatch.setattr(gpu.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout="Max retries exceeded", stderr=""))
    with pytest.raises(config.PipelineError, match="Nothing was started on Kaggle"):
        gpu.kaggle("kernels", "push")


def test_wavespeed_needs_its_key_and_a_single_named_shot(sb, monkeypatch):
    from pipeline import shots
    s = sb["shots"][0]
    s["motion"], s["animate"] = "clip", "wavespeed"
    assert shots.animator(sb, s) == "kaggle"                 # no key: the free GPU makes it
    monkeypatch.setenv("WAVESPEED_API_KEY", "fake-key-for-tests")
    assert shots.animator(sb, s) == "wavespeed"
    with pytest.raises(web.Refused, match="one chosen shot"):
        web.command(sb, "motion_wavespeed", {"ratios": ["9x16"]})
    assert web.command(sb, "motion_wavespeed", {"ratios": ["9x16"], "shots": ["s01"]})[0] == "motion"


def test_a_new_film_starts_with_camera_moves(monkeypatch):
    monkeypatch.setattr(providers, "gemini_json", lambda *a, **kw: draft(quoted="ana"))
    sb = script.new("word " * 20, "am", "home", "family", "close")[1]
    assert {s["motion"] for s in sb["shots"]} == {"camera"} and not storyboard.validate(sb)
