"""The studio's server: edits, limits, file access and job rules. No network, keys or model calls."""
import json
import shutil
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from pipeline import web
from pipeline.core import config


@pytest.fixture
def studio(tmp_path, monkeypatch):
    for name in ("outputs", "storyboards"):
        (tmp_path / name).mkdir()
    shutil.copy(config.ROOT / "storyboard.json", tmp_path / "storyboard.json")
    (tmp_path / "secret.png").write_bytes(b"no")
    folder = tmp_path / "outputs" / "one-percent"
    folder.mkdir()
    (folder / "a.mp4").write_bytes(b"0123456789")
    (folder / "web.log").write_text("log")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("SHOW_REPO_FILM", "1")
    monkeypatch.setattr(config, "OUTPUTS", tmp_path / "outputs")
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs.jsonl")
    started = []

    class Fake:
        def __init__(self, args, **k):
            started.append(args)
            self.code = None

        def poll(self):
            return self.code

        def terminate(self):
            self.code = 1
    monkeypatch.setattr(web.subprocess, "Popen", Fake)
    web.job.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}", data=None if body is None else json.dumps(body).encode(),
                                     headers={**({"Content-Type": "application/json"} if body is not None else {}), **(headers or {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    call.started, call.root = started, tmp_path
    yield call
    web.job.clear()
    server.shutdown()
    server.server_close()


def board(studio):
    return json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))


def test_pages_and_state_load(studio):
    for path in ("/", "/app.js", "/style.css", "/api/films", "/api/options", "/api/limits", "/api/job", "/api/film/one-percent"):
        assert studio(path)[0] == 200, path
    assert studio("/api/film/nope")[0] == 400


def test_edit_saves_one_shot_and_raises_the_version(studio):
    before = board(studio)
    assert studio("/api/film/one-percent/edit", {"shots": {"s02": {"narration": {"en": "New words."}, "emotion": "calm"}}})[0] == 200
    after = board(studio)
    assert after["version"] == before["version"] + 1
    assert [a["id"] for a, b in zip(after["shots"], before["shots"]) if a != b] == ["s02"]


@pytest.mark.parametrize("body", [
    {"shots": {"s99": {"emotion": "x"}}}, {"shots": {"s01": {"id": "s02"}}}, {"shots": {"s01": {"narration": {"en": ""}}}},
    {"references": {"mother": {"seed": 999}}}, {"music": {"seed": 5}}, {"consent": "yes"}, {"shots": {"s01": {"transition": {"type": "explode"}}}}, {"shots": 5}])
def test_bad_edits_save_nothing(studio, body):
    before = board(studio)
    assert studio("/api/film/one-percent/edit", body)[0] == 400
    assert board(studio) == before


def test_files_outside_outputs_are_never_served(studio):
    assert studio("/files/one-percent/a.mp4")[1] == b"0123456789"
    for path in ("/files/../secret.png", "/files/%2e%2e/secret.png", "/files/one-percent/../../secret.png", "/files/one-percent/web.log", "/files/..%5csecret.png"):
        assert studio(path)[0] == 404, path


def test_video_seeking(studio):
    assert studio("/files/one-percent/a.mp4", headers={"Range": "bytes=2-4"}) == (206, b"234")
    assert studio("/files/one-percent/a.mp4", headers={"Range": "bytes=-3"}) == (206, b"789")
    assert studio("/files/one-percent/a.mp4", headers={"Range": "bytes=50-"})[0] == 416


def test_other_sites_cannot_use_the_studio(studio):
    run = {"action": "build"}
    assert studio("/api/film/one-percent/run", run, {"Origin": "https://evil.example"})[0] == 403
    assert studio("/api/film/one-percent/run", run, {"Content-Type": "text/plain"})[0] == 403
    assert studio("/api/films", headers={"Host": "evil.example"})[0] == 403
    assert studio.started == []


def test_one_job_at_a_time_and_only_known_actions(studio):
    assert studio("/api/film/one-percent/run", {"action": "rm"})[0] == 400
    assert studio("/api/film/one-percent/run", {"action": "voice", "shots": ["--force"]})[0] == 400
    assert studio("/api/film/one-percent/run", {"action": "voice", "shots": ["s10"]})[0] == 200
    assert studio.started[0][-3:] == ["narration", "--shot", "s10"]
    assert studio("/api/film/one-percent/run", {"action": "build"})[0] == 400
    assert studio("/api/film/one-percent/edit", {"shots": {"s02": {"emotion": "x"}}})[0] == 400
    studio("/api/job/stop", {})
    assert json.loads(studio("/api/job")[1])["stopped"] is True


def test_building_never_calls_the_stage_that_generates(studio):
    studio("/api/film/one-percent/run", {"action": "build"})
    assert studio.started[0][-1] == "assemble"


def test_characters_are_chosen_before_pictures(studio):
    sb = board(studio)
    for r in sb["references"].values():
        r["reason"] = "Not chosen yet"
    (studio.root / "storyboard.json").write_text(json.dumps(sb), encoding="utf-8")
    assert studio("/api/film/one-percent/run", {"action": "pictures", "shots": ["s01"]})[0] == 400
    assert studio("/api/film/one-percent/run", {"action": "references", "name": "mother_older"})[0] == 400
    assert studio.started == []


def test_consent_lock(studio):
    sb = board(studio)
    sb["people"].update(based_on_real_people=True, consent="pending")
    (studio.root / "storyboard.json").write_text(json.dumps(sb), encoding="utf-8")
    assert studio("/api/film/one-percent/run", {"action": "voice"})[0] == 400
    assert studio("/api/film/one-percent/edit", {"consent": "My mother agreed in person on 25 November to the whole film."})[0] == 200
    assert studio("/api/film/one-percent/run", {"action": "voice"})[0] == 200


def test_uncollected_gpu_job_is_not_overwritten(studio):
    p = studio.root / "outputs" / "one-percent" / "jobs"
    p.mkdir()
    (p / "wan.json").write_text(json.dumps({"submitted": 1, "job": {"clips": []}}))
    assert studio("/api/film/one-percent/run", {"action": "motion_submit", "ratios": ["9x16"]})[0] == 400
    assert studio.started == []


def test_feedback_is_kept_word_for_word(studio):
    assert studio("/api/film/one-percent/feedback", {"who": "", "words": "x"})[0] == 400
    assert studio("/api/film/one-percent/feedback", {"test": "radio cut", "who": "friend, 24", "words": "በጣም ጥሩ ነው"})[0] == 200
    assert json.loads(studio("/api/film/one-percent")[1])["feedback"][0]["words"] == "በጣም ጥሩ ነው"
