"""Score a job against user_profile.yaml (0-100) with human-readable reasons."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import yaml

PROFILE_PATH = Path(__file__).resolve().parent.parent / "user_profile.yaml"

# Role families each preferred-role keyword maps onto.
_ROLE_HINTS = [
    (r"backend|python|fastapi|django|api", "Backend"),
    (r"full[- ]?stack|mern", "Full Stack"),
    (r"ml|machine learning|ai\b|data scien", "ML / AI"),
    (r"data scien", "Data Science"),
    (r"software|sde|developer|engineer", "Software Engineering"),
    (r"front[- ]?end|react", "Frontend"),
    (r"data engineer", "Data Engineering"),
    (r"devops|\bsre\b|site reliability|cloud|platform|infrastructure|kubernetes", "DevOps / SRE"),
]


_ADVANCED_DEGREE = re.compile(r"\b(ph\.?d|doctoral|postdoc|post-doc|masters?|m\.?tech|mba)\b", re.I)

# A PhD or Master's the description requires, not prefers. Read line by line ("B.E. or M.Tech"
# stays whole) and by section: Google lists "Master's or PhD" under Preferred qualifications.
_DEGREE_IN_TEXT = re.compile(r"\b(ph\.?\s?d\.?|doctorate|doctoral)\b|\bmaster'?s\b(\s+degree|\s+in\b|\s+from\b|"
                             r"\s+with\b)|\bmaster-?\s?/|\bm\.?\s?tech\b", re.I)
_DEGREE_OPTIONAL = re.compile(
    r"plus|prefer|nice to have|bonus|advantage|desirable|ideally|good to have|bachelor|\bb\.?\s?tech\b|"
    r"\bb\.?\s?e\b|\bbs\b|\bb\.?sc\b|undergrad|equivalent|or higher|or above|pursuing|student|intern|"
    r"\bor (relevant |equivalent |related |practical )?(work |industry )?experience|"
    # "...experience, or" opens a path without the degree, unless the "or" leads to another one
    r"experience\s*,?\s+or\b(?!\s+(an?\s+)?(ph\.?\s?d|doctor|master|m\.?\s?tech))|^or\b",
    re.I)
_SOFT_HEADING = re.compile(r"prefer|nice to have|good to have|bonus|desired|desirable|plus|added advantage", re.I)
_HEADING = re.compile(r"minimum|required|requirement|basic|must|qualification|who you are|"
                      r"what you('ll)? need|you have", re.I)


def needs_advanced_degree(description: str | None) -> str | None:
    """The line of a description that requires a PhD or Master's, if one does."""
    soft = False
    for line in re.split(r"\n+|•", description or ""):
        line = line.strip(" -*·o\t")
        if not line:
            continue
        if len(line) <= 60 and not _DEGREE_IN_TEXT.search(line) and (
                line.endswith(":") or _SOFT_HEADING.search(line) or _HEADING.search(line)):
            soft = bool(_SOFT_HEADING.search(line))      # a heading: what kind of section follows
            continue
        if not soft and _DEGREE_IN_TEXT.search(line) and not _DEGREE_OPTIONAL.search(line):
            return line
    return None


def _skill_pattern(skill: str) -> re.Pattern:
    core = re.split(r"\s*[/(]", skill.strip())[0].strip()
    return re.compile(r"(?<![\w+#])" + re.escape(core) + r"(?![\w+#])", re.I)


def save_pay_floors(min_lpa: float, target_lpa: float, path: str | Path | None = None) -> None:
    """Set min_lpa and target_lpa in user_profile.yaml, keeping every other line and comment.

    The file stays the one place the floors live; the web app's Pay menu edits it through
    this. Run a rescore afterwards: stored scores and pay verdicts depend on the floors.
    """
    if not 0 < min_lpa <= target_lpa <= 500:
        raise ValueError("need 0 < minimum <= target <= 500 (LPA)")
    file = Path(path or PROFILE_PATH)
    text = file.read_text(encoding="utf-8")
    for key, value in (("min_lpa", min_lpa), ("target_lpa", target_lpa)):
        text, found = re.subn(rf"^(\s*{key}:[ \t]*)[0-9.]+", lambda m: f"{m.group(1)}{value:g}",
                              text, count=1, flags=re.M)
        if not found:
            raise ValueError(f"no '{key}:' line under job_preferences in {file.name}")
    temp = file.with_suffix(".yaml.tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(file)                  # all at once: a crash never leaves half a profile
    load_profile.cache_clear()          # the cached copy still has the old floors


@lru_cache(maxsize=1)
def load_profile(path: str | None = None) -> dict:
    raw = yaml.safe_load(Path(path or PROFILE_PATH).read_text(encoding="utf-8")) or {}
    prefs = raw.get("job_preferences") or {}
    skills = raw.get("skills") or {}

    weighted: list[tuple[str, float, re.Pattern]] = []
    for group, weight in (("primary", 3.0), ("secondary", 1.5), ("ml_ai", 1.5)):
        for skill in skills.get(group) or []:
            weighted.append((skill, weight, _skill_pattern(skill)))

    levels = prefs.get("levels")
    if not levels:
        levels = ["Intern"] if str(prefs.get("type", "")).lower().startswith("intern") else ["Entry"]

    # Each preferred role maps to its most specific family ("DevOps Engineer" is DevOps / SRE,
    # not also generic Software Engineering), in the order listed: the first is the main target.
    families: list[str] = []
    for role in prefs.get("roles") or []:
        matched = [family for pattern, family in _ROLE_HINTS if re.search(pattern, role, re.I)]
        for family in [f for f in matched if f != "Software Engineering"] or matched:
            if family not in families:
                families.append(family)

    return {
        "raw": raw,
        "paid_only": bool(prefs.get("paid_only")),
        "target_lpa": float(prefs.get("target_lpa", 12)),
        "degree": str((raw.get("education") or {}).get("degree") or ""),
        "skills": weighted,
        "levels": levels,
        "families": families or ["Software Engineering", "Backend"],
        "locations": [l.lower() for l in prefs.get("preferred_locations") or []],
        "exclude": [k.lower() for k in prefs.get("exclude_keywords") or []],
    }


_PAY_EFFECT = {
    "target": (8, "Pay meets your target"),
    "ok": (4, "Pay meets your minimum"),
    "estimated": (2, "Estimated pay meets your minimum"),
    "low": (-35, "Pay is below your minimum"),
    "unpaid": (-60, "Unpaid"),
    "suspicious": (-70, "Looks like a fake or pay-to-join listing"),
}

# Points for a job's level given the levels the user is targeting.
_ADJACENT = {
    "Intern": {"Entry": 22, "Unspecified": 10},
    "Entry": {"Intern": 18, "Unspecified": 18, "Mid": 8},
    "Mid": {"Entry": 20, "Unspecified": 20, "Senior": 10},
}


def score_job(job: dict, profile: dict | None = None) -> tuple[float, list[str]]:
    profile = profile or load_profile()
    reasons: list[str] = []
    score = 0.0
    title = job.get("title") or ""
    text = f"{title}\n{job.get('description') or ''}"

    def add(points: float, why: str) -> None:
        nonlocal score
        score += points
        if points:
            reasons.append(f"{why} {'+' if points > 0 else '−'}{abs(points):g}")

    # Level (35)
    level = job.get("level") or "Unspecified"
    if level in profile["levels"]:
        add(35, f"{level} role")
    else:
        best = max((_ADJACENT.get(t, {}).get(level, 0) for t in profile["levels"]), default=0)
        if best:
            add(best, f"{level}, next to your level")
        else:
            reasons.append(f"{level} level is outside your target")

    # Skills (35): about six primary skills for full marks, so more of yours ranks higher
    hits = [(name, w) for name, w, pat in profile["skills"] if pat.search(text)]
    if hits:
        got = sum(w for _, w in hits)
        add(round(min(35.0, 35.0 * got / 18.0)), "Skills: " + ", ".join(n for n, _ in hits[:6]))
    elif not job.get("description"):
        add(8, "No description yet")       # not punished for skills it cannot show

    # Role family (15): the main target role full, your other roles less
    role = job.get("role") or "Other"
    families = profile["families"]
    if families and role == families[0]:
        add(15, f"{role}, your main role")
    elif role in families:
        add(10, f"{role}, one of your roles")
    elif job.get("is_tech"):
        add(7, "Other tech role")

    # Location (10)
    loc = (job.get("location") or "").lower()
    cities = [c.lower() for c in job.get("cities") or []]
    wants = profile["locations"]
    if (job.get("is_remote") and "remote" in wants) or any(
        w in cities or (w != "india" and w in loc) for w in wants
    ):
        add(10, "Preferred location")
    elif "india" in wants and job.get("scope") == "india":
        add(6, "In India")

    # Freshness (5)
    stamp = job.get("posted_at") or job.get("first_seen") or ""
    try:
        posted = datetime.fromisoformat(stamp[:10]).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - posted <= timedelta(days=7):
            add(5, "Posted this week")
    except ValueError:
        pass

    # Aggregator listings come from companies nobody vetted for the tracked list,
    # so at equal fit they rank below a tracked company's own posting.
    if job.get("source") in ("linkedin", "internshala"):
        add(-10, "From an aggregator")

    # Experience, degree, pay and excluded keywords
    exp_min = job.get("exp_min")
    if exp_min is not None and exp_min >= 3 and set(profile["levels"]) <= {"Intern", "Entry"}:
        add(-25, f"Asks for {exp_min:g}+ years")
    has_advanced = _ADVANCED_DEGREE.search(profile["degree"])
    if not has_advanced and (_ADVANCED_DEGREE.search(title) or needs_advanced_degree(job.get("description"))):
        add(-30, "Requires a PhD or Master's")
    verdict = job.get("pay_verdict") or "unknown"
    if verdict == "estimated" and (job.get("est_min_lpa") or 0) >= profile["target_lpa"]:
        add(8, "Estimated pay meets your target")
    elif verdict == "unknown" and job.get("source") in ("linkedin", "internshala"):
        # No stated pay and a company we know nothing about: most of the low-paid
        # and unpaid listings live here, so they should not outrank known payers.
        add(-15, "Pay unknown")
    elif verdict in _PAY_EFFECT:
        add(*_PAY_EFFECT[verdict])
    lowered = title.lower()
    for word in profile["exclude"]:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            add(-20, f"Excluded keyword: {word}")
            break

    return max(0.0, min(100.0, round(score, 1))), reasons
