"""A person approves each shot's script, then its voice, then its picture. Each step stays locked until the one before it.

Approval is of exact content: if a line, a voice or a picture changes, its approval no longer counts.
Storyboards without an `approvals` field (made before this rule) are not gated. The `film` command is not gated either: it is the one
command that rebuilds a film from its storyboard without stopping. Consent is a separate lock and always holds.
"""
from contextvars import ContextVar

from . import cache, config

_review: ContextVar[bool] = ContextVar("review", default=True)


def no_review():
    _review.set(False)


def script_key(shot):
    return cache.key({"narration": shot["narration"], "quote_voice": shot.get("quote_voice")})


def ok(sb, kind, name, key):
    """A missing thing (key None) is never approved."""
    return not _review.get() or "approvals" not in sb or (key is not None and sb["approvals"].get(kind, {}).get(name) == key)


def need(sb, kind, name, key):
    if not ok(sb, kind, name, key):
        raise config.PipelineError(f"{name}: approve the {kind} first (python -m pipeline approve {kind} --shot {name[:3]}).")


def give(sb, kind, name, key):
    sb.setdefault("approvals", {}).setdefault(kind, {})[name] = key
