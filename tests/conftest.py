import pytest

from pipeline.core import approvals, config, runlog


@pytest.fixture(autouse=True)
def own_log(tmp_path, monkeypatch):
    """Tests never read or write the real call log, personal films or settings."""
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "FILMS", tmp_path / "my-films")
    monkeypatch.delenv("SHOW_REPO_FILM", raising=False)
    token = runlog._private.set(False)
    review = approvals._review.set(True)
    yield
    approvals._review.reset(review)
    runlog._private.reset(token)
