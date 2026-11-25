"""Content-addressed cache. Each output has a .meta.json holding the hash of its inputs."""
import hashlib
import json
import os
import time
from pathlib import Path


_known: dict = {}


def file_sha(path: Path) -> str:
    """Remembered while the file's size and time stay the same, so a page does not re-read every file."""
    st = path.stat()
    mark = (st.st_size, st.st_mtime_ns)
    hit = _known.get(str(path))
    # A file touched in the last two seconds may change again within the clock's resolution: never trust the memory for it.
    if hit and hit[0] == mark and time.time() - st.st_mtime > 2:
        return hit[1]
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    _known[str(path)] = (mark, sha)
    return sha


def key(inputs: dict) -> str:
    blob = json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def read_meta(path: Path) -> dict:
    try:
        return json.loads(meta_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def fresh(path: Path, inputs: dict) -> bool:
    """True if the file exists, was made from these inputs and has not been altered."""
    meta = read_meta(path)
    return path.exists() and meta.get("key") == key(inputs) and meta.get("sha256") == file_sha(path)


def store(path: Path, data: bytes, inputs: dict, **extra) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    os.replace(part, path)
    stamp(path, inputs, **extra)


def stamp(path: Path, inputs: dict, **extra) -> None:
    meta = {"key": key(inputs), "sha256": file_sha(path), "inputs": inputs, **extra}
    target = meta_path(path)
    part = target.with_name(target.name + ".part")
    part.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    os.replace(part, target)
