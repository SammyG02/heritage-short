"""runs.jsonl: one line per attempted model call, including failures."""
import hashlib
import json
import os
import re
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter

from . import config

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]
_SECRET_NAMES = ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
                 "KAGGLE_API_TOKEN", "KAGGLE_KEY", "HF_TOKEN", "ADDIS_API_KEY", "GROQ_API_KEY", "WAVESPEED_API_KEY")


# A free limit belongs to one account. Each call notes which one, as a short one-way fingerprint, never the key itself.
_ACCOUNT_OF = {"gemini": "GEMINI_API_KEY", "cloudflare": "CLOUDFLARE_ACCOUNT_ID", "wavespeed": "WAVESPEED_API_KEY"}


def progress(k, n, what):
    """A line the studio turns into its progress bar."""
    print(f"progress {k} of {n}: {what}", flush=True)


def step(what):
    """What is happening right now, in plain words, shown under the progress bar."""
    print(f"step: {what}", flush=True)


def account(provider):
    v = os.environ.get(_ACCOUNT_OF.get(provider, ""), "").strip()
    return hashlib.sha256(v.encode()).hexdigest()[:8] if v else None


_private: ContextVar[bool] = ContextVar("private", default=False)


def use_private():
    """From here on, calls are logged with the personal films, not in the repository's runs.jsonl."""
    _private.set(True)


def file():
    if not _private.get():
        return config.RUNS
    config.FILMS.mkdir(parents=True, exist_ok=True)
    return config.FILMS / "runs.jsonl"


def redact(text: str) -> str:
    for name in _SECRET_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            text = text.replace(value, f"<{name}>")
    return re.sub(r"AIza[\w-]{20,}|gsk_\w{20,}", "<key>", text)


_writing = threading.Lock()


def write(record: dict) -> None:
    line = redact(json.dumps(record, ensure_ascii=False))
    with _writing, file().open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


@contextmanager
def call(stage, item, provider, model, params, seed=None, attempt=1):
    """Time a model call. The block may add gpu_s, list_price_usd, output or usage."""
    record = {"run_id": RUN_ID, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "stage": stage, "item": item, "provider": provider, "model": model, "params": params,
              "seed": seed, "attempt": attempt, "status": "ok", "latency_s": None, "gpu_s": None,
              "cost_usd": 0.0, "list_price_usd": None, "output": None, "error": None}
    if account(provider):
        record["account"] = account(provider)
    start = perf_counter()
    try:
        yield record
    except BaseException as e:
        record["status"] = "error"
        record["error"] = str(e)[:600] or type(e).__name__
        raise
    finally:
        record["latency_s"] = round(perf_counter() - start, 3)
        write(record)
