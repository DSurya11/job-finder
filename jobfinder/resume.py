"""The resume as text, for agents that compare it with a job. Contact details never leave.

Everything an agent reads is sent to the model's provider, so the lines that identify the
person (the name heading, email, phone, links) are removed here, the same rule as the
profile tool (agent_tools.get_my_profile).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml
from pypdf import PdfReader

from . import score

_CONTACT = re.compile(
    r"@|https?://|www\.|linkedin|github\.com|leetcode|\+?\d[\d\s().-]{8,}\d", re.I)


def resume_path() -> Path | None:
    profile = Path(score.PROFILE_PATH)
    raw = yaml.safe_load(profile.read_text(encoding="utf-8")) or {}
    value = raw.get("resume_path")
    if not value:
        return None
    path = (profile.parent / value).resolve()
    return path if path.exists() else None


def resume_text() -> str:
    """The resume's text without contact lines, or "" when there is none."""
    path = resume_path()
    return _read(str(path), path.stat().st_mtime) if path else ""


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> str:          # mtime: a new resume file is read again
    text = "\n".join((page.extract_text() or "") for page in PdfReader(path).pages)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if lines:
        lines = lines[1:]                            # the heading line is the person's name
    personal = _personal_values()
    kept = [line for line in lines
            if not _CONTACT.search(line) and not any(v and v.lower() in line.lower() for v in personal)]
    return "\n".join(kept)


def _personal_values() -> list[str]:
    raw = yaml.safe_load(Path(score.PROFILE_PATH).read_text(encoding="utf-8")) or {}
    personal = raw.get("personal") or {}
    return [str(personal.get(k) or "").strip() for k in ("name", "email", "phone")]

