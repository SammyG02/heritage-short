"""Paths, secrets and external tools."""
import glob
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
RUNS = ROOT / "runs.jsonl"
load_dotenv(ROOT / ".env")
# Everyone's own stories, pictures, voices, music and call log. Never part of the code: Git ignores it.
FILMS = Path(os.environ.get("HERITAGE_FILMS", "").strip() or ROOT / "my-films")
SCHEMA = ROOT / "schema" / "storyboard.schema.json"
FONT = ROOT / "assets" / "fonts" / "NotoSansEthiopic.ttf"


class PipelineError(RuntimeError):
    """A failure with a message meant for the person running the pipeline."""


def secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise PipelineError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return value


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    # winget installs FFmpeg without updating PATH in shells that are already open.
    hits = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                  "Microsoft/WinGet/Packages/Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
    if hits:
        return hits[0]
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(args: list, cwd: Path | None = None) -> str:
    """Run FFmpeg and return its stderr, which is where it reports measurements."""
    cmd = [ffmpeg(), "-hide_banner", "-nostdin", "-y", *map(str, args)]
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode:
        raise PipelineError("FFmpeg failed:\n" + p.stderr[-2500:])
    return p.stderr
