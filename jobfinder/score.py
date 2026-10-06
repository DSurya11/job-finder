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
    (r"devops|sre|cloud", "DevOps / SRE"),
]


_ADVANCED_DEGREE = re.compile(r"\b(ph\.?d|doctoral|postdoc|post-doc|masters?|m\.?tech|mba)\b", re.I)


def _skill_pattern(skill: str) -> re.Pattern:
    core = re.split(r"\s*[/(]", skill.strip())[0].strip()
    return re.compile(r"(?<![\w+#])" + re.escape(core) + r"(?![\w+#])", re.I)


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

    families: list[str] = []
    for role in prefs.get("roles") or []:
        for pattern, family in _ROLE_HINTS:
            if re.search(pattern, role, re.I) and family not in families:
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

    # Level fit (35)
    level = job.get("level") or "Unspecified"
    if level in profile["levels"]:
        score += 35
        reasons.append(f"{level} role")
    else:
        best = max((_ADJACENT.get(t, {}).get(level, 0) for t in profile["levels"]), default=0)
        score += best
        if best == 0:
            reasons.append(f"{level} level is outside your target")

    # Skills (35)
    hits = [(name, w) for name, w, pat in profile["skills"] if pat.search(text)]
    if hits:
        got = sum(w for _, w in hits)
        score += min(35.0, 35.0 * got / 9.0)   # ~3 primary skills maxes this out
        reasons.append("Skills: " + ", ".join(n for n, _ in hits[:6]))
    elif not job.get("description"):
        score += 8  # no description yet, so do not punish it for missing skills

    # Role family (15)
    role = job.get("role") or "Other"
    if role in profile["families"]:
        score += 15
        reasons.append(f"{role} matches your roles")
    elif job.get("is_tech"):
        score += 7

    # Location (10)
    loc = (job.get("location") or "").lower()
    cities = [c.lower() for c in job.get("cities") or []]
    wants = profile["locations"]
    if (job.get("is_remote") and "remote" in wants) or any(
        w in cities or (w != "india" and w in loc) for w in wants
    ):
        score += 10
        reasons.append("Preferred location")
    elif "india" in wants and job.get("scope") == "india":
        score += 6

    # Freshness (5)
    stamp = job.get("posted_at") or job.get("first_seen") or ""
    try:
        posted = datetime.fromisoformat(stamp[:10]).replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - posted <= timedelta(days=7):
            score += 5
            reasons.append("Posted this week")
    except ValueError:
        pass

    # Aggregator listings come from companies nobody vetted for the tracked list,
    # so at equal fit they rank below a tracked company's own posting.
    if job.get("source") in ("linkedin", "internshala"):
        score -= 10

    # Experience mismatch and excluded keywords
    exp_min = job.get("exp_min")
    if exp_min is not None and exp_min >= 3 and set(profile["levels"]) <= {"Intern", "Entry"}:
        score -= 25
        reasons.append(f"Asks for {exp_min:g}+ years")
    if _ADVANCED_DEGREE.search(title) and not _ADVANCED_DEGREE.search(profile["degree"]):
        score -= 30
        reasons.append("Aimed at PhD / Master's candidates")
    verdict = job.get("pay_verdict") or "unknown"
    if verdict == "estimated" and (job.get("est_min_lpa") or 0) >= profile["target_lpa"]:
        score += 8
        reasons.append("Estimated pay meets your target")
    elif verdict == "unknown" and job.get("source") in ("linkedin", "internshala"):
        # No stated pay and a company we know nothing about: most of the low-paid
        # and unpaid listings live here, so they should not outrank known payers.
        score -= 15
        reasons.append("Pay unknown")
    elif verdict in _PAY_EFFECT:
        delta, why = _PAY_EFFECT[verdict]
        score += delta
        reasons.append(why)
    lowered = title.lower()
    for word in profile["exclude"]:
        if re.search(r"\b" + re.escape(word) + r"\b", lowered):
            score -= 20
            reasons.append(f"Excluded keyword: {word}")
            break

    return max(0.0, min(100.0, round(score, 1))), reasons
