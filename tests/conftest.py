from pathlib import Path

import pytest

from pipeline.core import approvals, config, runlog

# A fixed copy, so working on the real film never breaks a test.
BOARD = Path(__file__).parent / "data" / "storyboard.json"


@pytest.fixture(autouse=True)
def own_log(tmp_path, monkeypatch):
    """Tests never read or write the real call log, personal films or settings."""
    monkeypatch.setattr(config, "RUNS", tmp_path / "runs.jsonl")
    monkeypatch.setattr(config, "FILMS", tmp_path / "my-films")
    for name in ("SHOW_REPO_FILM", "ADDIS_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    token = runlog._private.set(False)
    review = approvals._review.set(True)
    yield
    approvals._review.reset(review)
    runlog._private.reset(token)
