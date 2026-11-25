"""runs.jsonl: one line per attempted model call, including failures."""
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from time import perf_counter

from . import config

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:4]
_SECRET_NAMES = ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
                 "KAGGLE_API_TOKEN", "KAGGLE_KEY", "HF_TOKEN")


def redact(text: str) -> str:
    for name in _SECRET_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            text = text.replace(value, f"<{name}>")
    return re.sub(r"AIza[\w-]{20,}", "<key>", text)


def write(record: dict) -> None:
    line = redact(json.dumps(record, ensure_ascii=False))
    with config.RUNS.open("a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


@contextmanager
def call(stage, item, provider, model, params, seed=None, attempt=1):
    """Time a model call. The block may add gpu_s, list_price_usd, output or usage."""
    record = {"run_id": RUN_ID, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "stage": stage, "item": item, "provider": provider, "model": model, "params": params,
              "seed": seed, "attempt": attempt, "status": "ok", "latency_s": None, "gpu_s": None,
              "cost_usd": 0.0, "list_price_usd": None, "output": None, "error": None}
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
