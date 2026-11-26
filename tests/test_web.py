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
from tests.conftest import BOARD


@pytest.fixture
def studio(tmp_path, monkeypatch):
    for name in ("outputs", "storyboards"):
        (tmp_path / name).mkdir()
    shutil.copy(BOARD, tmp_path / "storyboard.json")
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


def test_home_shows_every_film_and_its_next_step(studio):
    cards = json.loads(studio("/api/home")[1])
    assert [c["id"] for c in cards] == ["one-percent"]
    assert cards[0]["step"] == "script" and cards[0]["film"] is False and cards[0]["poster"] is None
    assert cards[0]["done"][0] == ["Voices", 0, 12]


def test_a_damaged_film_does_not_hide_the_others(studio):
    sb = board(studio)
    sb.update(id="broken-film", references={"x": {}})
    (studio.root / "storyboards" / "b.json").write_text(json.dumps(sb), encoding="utf-8")
    assert [c["id"] for c in json.loads(studio("/api/home")[1])] == ["one-percent", "broken-film"]


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


def test_building_never_calls_the_stage_that_generates(studio, monkeypatch):
    monkeypatch.setattr(web.approvals, "ok", lambda *a: True)  # everything approved
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


def test_the_studio_builds_only_an_approved_film(studio, monkeypatch):
    monkeypatch.setattr(web.approvals, "ok", lambda *a: False)
    code, body = studio("/api/film/one-percent/run", {"action": "build"})
    assert code == 400 and b"Approve these first" in body and studio.started == []


def test_characters_can_be_added_changed_extended_and_removed():
    from pipeline.core import storyboard
    sb = json.loads(BOARD.read_text(encoding="utf-8"))
    web.character(sb, {"name": "Grandmother", "look": "an Ethiopian woman in her seventies, grey hair, white netela", "shots": ["s01"]})
    g = sb["references"]["grandmother"]
    assert g["reason"] == "Not chosen yet" and "grandmother" in sb["shots"][0]["references"] and not storyboard.validate(sb)
    web.character(sb, {"name": "grandmother", "more_faces": 2})
    assert len(g["seeds"]) == 4
    web.character(sb, {"name": "grandmother", "look": "the same woman, now in a green dress", "shots": []})
    assert "green dress" in g["prompt"] and "grandmother" not in sb["shots"][0]["references"]
    web.character(sb, {"name": "grandmother", "remove": True})
    assert "grandmother" not in sb["references"]
    with pytest.raises(web.Refused):
        web.character(sb, {"name": "x", "look": "too short"})


def test_consent_can_be_added_to_and_withdrawn(studio):
    code, _ = studio("/api/film/one-percent/edit", {"consent_add": "My father agreed in person on 26 November to the public film."})
    assert code == 200
    board_now = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    assert "My father agreed" in board_now["people"]["consent_record"]
    studio("/api/film/one-percent/edit", {"consent_withdraw": True})
    board_now = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    assert board_now["people"]["consent"] == "pending" and "withdrawn" in board_now["people"]["consent_record"]


def _photo_b64():
    import base64
    import io
    from PIL import Image
    im = Image.new("RGB", (2000, 1500), (180, 120, 90))
    buf = io.BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # camera maker: must not survive
    im.save(buf, "JPEG", exif=exif)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def test_a_photo_needs_that_persons_yes_and_leaves_with_it(studio):
    from PIL import Image
    from pipeline import keyframes
    from pipeline.core import storyboard
    code, body = studio("/api/film/one-percent/photo", {"name": "mother", "person": "mother", "image": _photo_b64()})
    assert code == 400 and b"their photo used as a reference" in body                     # no yes recorded
    mother = {"role": "mother", "story": True, "likeness": True, "words": False, "photo": True, "how": "in person, 26 November"}
    assert studio("/api/film/one-percent/edit", {"people_agreed": [mother]})[0] == 200
    assert studio("/api/film/one-percent/photo", {"name": "mother", "person": "mother", "image": _photo_b64()})[0] == 200
    sb = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    photo = keyframes.photo_path(sb, "mother")
    im = Image.open(photo)
    assert max(im.size) == 1024 and not im.getexif() and sb["people"]["real_people"] is True and not storyboard.validate(sb)
    assert sb["references"]["mother"]["reason"] == "Not chosen yet" and storyboard.PHOTO_NOTE in sb["people"]["statement"]
    assert "photo" in keyframes.ref_inputs(sb, "mother", 11)["prompt"] or "reference photo" in keyframes.ref_inputs(sb, "mother", 11)["prompt"]
    # the person changes their mind: the photo goes, and the film is invented again
    assert studio("/api/film/one-percent/edit", {"people_agreed": [{**mother, "photo": False}]})[0] == 200
    sb = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    assert not photo.exists() and "photo" not in sb["references"]["mother"] and sb["people"]["real_people"] is False


def test_photos_never_go_into_git():
    import subprocess
    r = subprocess.run(["git", "check-ignore", "-q", "outputs/one-percent/references/photos/mother.png"], cwd=config.ROOT)
    assert r.returncode == 0


def test_edits_still_work_when_paid_shots_already_pass_the_budget(studio, monkeypatch):
    from pipeline import wavespeed
    monkeypatch.setenv("WAVESPEED_API_KEY", "fake-key-for-tests")  # WaveSpeed only counts with its key
    monkeypatch.setattr(wavespeed, "left", lambda fresh=False: 0.10)
    sb = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    for s in sb["shots"]:
        s["motion"], s["animate"] = "clip", "wavespeed"
    (studio.root / "storyboard.json").write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    assert studio("/api/film/one-percent/edit", {"shots": {"s07": {"redraw": "9x16"}}})[0] == 200          # a redraw adds nothing
    assert studio("/api/film/one-percent/edit", {"shots": {"s07": {"animate": "kaggle"}}})[0] == 200       # moving to Kaggle lowers it
    sb = json.loads((studio.root / "storyboard.json").read_text(encoding="utf-8"))
    sb["shots"][6]["motion"] = "camera"
    (studio.root / "storyboard.json").write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    code, _ = studio("/api/film/one-percent/edit", {"shots": {"s07": {"motion": "clip", "animate": "wavespeed"}}})
    assert code == 400                                                                                     # adding a paid shot past the money is refused
