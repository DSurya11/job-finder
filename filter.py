"""Job filter pipeline — FTE-only, India, fresher roles.

This module applies all filter criteria AFTER fetching raw data from any ATS.
The pipeline is:
  1. FTE hard filter (employment type field + title/description patterns)
  2. Location include filter (India / Remote only)
  3. Title include filter (SDE / Software Engineer / Backend / etc.)
  4. Seniority exclude filter (Senior / Staff / Lead / etc.)
  5. Experience exclude filter (3+ years / 5+ years / etc.)
  6. Deduplication by (company + normalised title + location)
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)


# ── FTE Hard Filter ──────────────────────────────────────────────────────────

# Patterns that indicate internship / non-FTE (case-insensitive)
_INTERN_PATTERNS = [
    re.compile(r"\bintern\b", re.IGNORECASE),
    re.compile(r"\binternship\b", re.IGNORECASE),
    re.compile(r"\bco-?op\b", re.IGNORECASE),
    re.compile(r"\btrainee\s+program\b", re.IGNORECASE),
]

# Exception: Graduate Engineer Trainee is a real FTE designation
_GET_PATTERN = re.compile(
    r"\bgraduate\s+engineer\s+trainee\b", re.IGNORECASE
)

# Employment type values that pass the FTE filter
_FTE_EMPLOYMENT_TYPES = {
    "full-time", "full time", "fulltime", "regular", "permanent",
}

# Employment type values that are definitely NOT FTE
_NON_FTE_EMPLOYMENT_TYPES = {
    "internship", "intern", "part-time", "part time", "contract",
    "temporary", "co-op", "coop", "trainee",
}


def _is_fte(job: dict) -> bool:
    """Return True if the job passes the FTE hard filter."""
    title = job.get("title", "")
    description = job.get("description", "")
    employment_type = (job.get("employment_type") or "").strip().lower()

    # 1. If the ATS provides a reliable employment type field, use it
    if employment_type and employment_type != "unknown":
        if employment_type in _NON_FTE_EMPLOYMENT_TYPES:
            return False
        if employment_type in _FTE_EMPLOYMENT_TYPES:
            # Even if field says FTE, still check title for intern keywords
            pass  # fall through to title check below
        # Unknown value — fall through

    combined = f"{title} {description}"

    # 2. Check for Graduate Engineer Trainee exception FIRST
    if _GET_PATTERN.search(combined):
        return True

    # 3. Check for intern/co-op patterns in title and description
    for pattern in _INTERN_PATTERNS:
        if pattern.search(title):
            return False
        # For description, only check if the word appears in a job-type context
        # (avoid false positives from "internal" etc.)
        if pattern.search(description[:500]):
            # Extra check: "intern" inside "internal" is a false positive
            if pattern.pattern == r"\bintern\b":
                # Make sure it's not "internal", "internationally", etc.
                for m in re.finditer(r"\bintern\b", description[:500], re.IGNORECASE):
                    after = description[m.end():m.end() + 5].lower()
                    if not after.startswith(("al", "at", "ment")):
                        return False
            else:
                return False

    return True


# ── Location Include Filter ──────────────────────────────────────────────────

_INDIA_LOCATIONS = {
    "india", "bangalore", "bengaluru", "hyderabad", "pune", "chennai",
    "mumbai", "delhi", "new delhi", "noida", "gurugram", "gurgaon",
    "ahmedabad", "jaipur", "kolkata", "bhopal", "indore", "kochi",
    "thiruvananthapuram", "lucknow", "jabalpur",
}

_REMOTE_KEYWORDS = {"remote", "work from home", "wfh", "anywhere"}

# Countries/regions that disqualify a "Remote" listing
_NON_INDIA_MARKERS = {
    "usa", "us ", " us", "united states", "brazil", "uk", "united kingdom",
    "canada", "australia", "germany", "france", "singapore", "japan",
    "china", "korea", "ireland", "netherlands", "sweden", "portugal",
    "new york", "san francisco", "seattle", "london", "toronto", "sydney",
    "berlin", "paris", "dublin", "amsterdam", "sao paulo", "tokyo",
    "emea", "latam", "apac", "uae", "united arab emirates", "dubai", "middle east",
}


def _is_india_or_remote(job: dict) -> bool:
    """Return True if location is India-based or genuinely global/unqualified Remote."""
    location = (job.get("location") or "").lower()

    # Check for explicit India locations first
    if any(loc in location for loc in _INDIA_LOCATIONS):
        return True

    # Check for remote — but reject if tied to a non-India country
    if any(kw in location for kw in _REMOTE_KEYWORDS):
        # If location also mentions a non-India country, reject it
        if any(marker in location for marker in _NON_INDIA_MARKERS):
            return False
        return True  # unqualified remote — keep

    # If location is empty, it might be a global/remote posting — keep it
    if not location.strip():
        return True

    return False


# ── Title Include Filter ─────────────────────────────────────────────────────

_TITLE_INCLUDE_PATTERNS = [
    re.compile(r"\bsde\b", re.IGNORECASE),
    re.compile(r"\bsdet\b", re.IGNORECASE),
    re.compile(r"\bsoftware\s+(?:engineer|developer|dev)\b", re.IGNORECASE),
    re.compile(r"\bbackend\b", re.IGNORECASE),
    re.compile(r"\bfull\s*stack\b", re.IGNORECASE),
    re.compile(r"\bnew\s+grad\b", re.IGNORECASE),
    re.compile(r"\bgraduate\s+engineer\s+trainee\b", re.IGNORECASE),
    re.compile(r"\bmember\s+of\s+technical\s+staff\b", re.IGNORECASE),
    re.compile(r"\b(?:MTS|AMTS)\b"),
    re.compile(r"\bdeveloper\b", re.IGNORECASE),
    re.compile(r"\bfrontend\b", re.IGNORECASE),
    re.compile(r"\bplatform\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bsite\s+reliability\b", re.IGNORECASE),
    re.compile(r"\bdevops\b", re.IGNORECASE),
    re.compile(r"\bdata\s+(?:engineer|scientist)\b", re.IGNORECASE),
    re.compile(r"\bml\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bmachine\s+learning\b", re.IGNORECASE),
    re.compile(r"\bai\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bcloud\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bsecurity\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bsystems?\s+engineer\b", re.IGNORECASE),
    re.compile(r"\bapplication\s+(?:engineer|developer)\b", re.IGNORECASE),
    re.compile(r"\bcomputer\s+scientist\b", re.IGNORECASE),
]


def _title_matches(job: dict) -> bool:
    """Return True if the title matches at least one include pattern."""
    title = job.get("title", "")
    return any(p.search(title) for p in _TITLE_INCLUDE_PATTERNS)


# ── Seniority Exclude Filter ────────────────────────────────────────────────

_SENIORITY_EXCLUDE_PATTERNS = [
    re.compile(r"\bsenior\b", re.IGNORECASE),
    re.compile(r"\bsr\.?\b", re.IGNORECASE),
    re.compile(r"\bstaff\b", re.IGNORECASE),
    re.compile(r"\bprincipal\b", re.IGNORECASE),
    re.compile(r"\blead\b", re.IGNORECASE),
    re.compile(r"\bmanager\b", re.IGNORECASE),
    re.compile(r"\bdirector\b", re.IGNORECASE),
    re.compile(r"\bvp\b", re.IGNORECASE),
    re.compile(r"\bvice\s+president\b", re.IGNORECASE),
    re.compile(r"\bhead\s+of\b", re.IGNORECASE),
    re.compile(r"\barchitect\b", re.IGNORECASE),
    re.compile(r"\bfellow\b", re.IGNORECASE),
    re.compile(r"\bdistinguished\b", re.IGNORECASE),
    re.compile(r"\bsde-?3\b", re.IGNORECASE),
    re.compile(r"\bl[6-9]\b", re.IGNORECASE),
    # Pre-sales / solutions sales — not software development roles
    re.compile(r"\bpre-?sales\b", re.IGNORECASE),
]


_FRESHER_EXCEPTIONS = re.compile(r"\b(new\s+grad|graduate|fresher)\b", re.IGNORECASE)

def _is_senior(job: dict) -> bool:
    """Return True if the title indicates a senior/leadership role."""
    title = job.get("title", "")
    
    # Check word-based senior markers
    if any(p.search(title) for p in _SENIORITY_EXCLUDE_PATTERNS):
        return True
        
    # Check numeric levels (e.g. Engineer III) which typically require experience
    _NUMERIC_SENIORITY_PATTERN = re.compile(r"\b([3-9]|iii|iv|v|vi)\b", re.IGNORECASE)
    if _NUMERIC_SENIORITY_PATTERN.search(title):
        # Ignore numeric levels if the title explicitly says New Grad/Fresher
        if not _FRESHER_EXCEPTIONS.search(title):
            return True
            
    return False


# ── Experience Exclude Filter ────────────────────────────────────────────────

# Matches "2+ years", "5+ years", "3-5 years", "7 to 11 years", "8 years", etc.
_EXP_PATTERN = re.compile(
    r"\b([2-9]|[1-9]\d)\+?\s*(?:(?:to|-)\s*\d+\s*)?years?\b", re.IGNORECASE
)

def _requires_experience(job: dict) -> bool:
    """Return True if the title or description explicitly requires 2+ years experience."""
    combined = job.get("title", "") + " " + job.get("description", "")
    # Check the entire description since Amazon puts qualifications at the very end
    return bool(_EXP_PATTERN.search(combined))


# ── Deduplication ────────────────────────────────────────────────────────────

def _normalise_text(text: str) -> str:
    """Lowercase, strip, remove punctuation for dedup key."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _dedup_key(job: dict) -> str:
    company = _normalise_text(job.get("company", ""))
    title = _normalise_text(job.get("title", ""))
    location = _normalise_text(job.get("location", ""))
    return f"{company}|{title}|{location}"


def deduplicate(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs based on (company, title, location)."""
    seen: set[str] = set()
    unique: list[dict] = []
    for job in jobs:
        key = _dedup_key(job)
        if key not in seen:
            seen.add(key)
            unique.append(job)
    dropped = len(jobs) - len(unique)
    if dropped:
        logger.info("Dedup: removed %d duplicates, %d unique remain", dropped, len(unique))
    return unique


# ── Main Pipeline ────────────────────────────────────────────────────────────

def apply_filters(jobs: list[dict]) -> list[dict]:
    """Run the full filter pipeline on raw fetched jobs.

    Returns:
        Filtered, deduplicated list of fresher FTE jobs in India.
    """
    total = len(jobs)

    # Step 1: FTE hard filter
    jobs = [j for j in jobs if _is_fte(j)]
    logger.info("After FTE filter: %d / %d", len(jobs), total)

    # Step 2: Location filter
    jobs = [j for j in jobs if _is_india_or_remote(j)]
    logger.info("After location filter: %d", len(jobs))

    # Step 3: Title include filter
    jobs = [j for j in jobs if _title_matches(j)]
    logger.info("After title filter: %d", len(jobs))

    # Step 4: Seniority exclude filter
    jobs = [j for j in jobs if not _is_senior(j)]
    logger.info("After seniority filter: %d", len(jobs))

    # Step 5: Experience exclude filter
    jobs = [j for j in jobs if not _requires_experience(j)]
    logger.info("After experience filter: %d", len(jobs))

    # Step 6: Dedup
    jobs = deduplicate(jobs)
    logger.info("Final count after dedup: %d", len(jobs))

    return jobs
