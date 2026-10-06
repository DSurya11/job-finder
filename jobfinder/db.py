"""SQLite store: jobs, your application status per job, and per-company run health."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT,
    cities TEXT,                 -- JSON list of canonical Indian cities
    is_remote INTEGER DEFAULT 0,
    scope TEXT,                  -- india | remote_global | unknown
    employment_type TEXT,
    level TEXT,
    role TEXT,
    is_tech INTEGER DEFAULT 0,
    exp_min REAL,
    exp_max REAL,
    salary_min_lpa REAL,
    salary_max_lpa REAL,
    salary_text TEXT,
    description TEXT,
    departments TEXT,
    apply_url TEXT,
    source TEXT,
    posted_at TEXT,
    first_seen TEXT,
    last_seen TEXT,
    is_active INTEGER DEFAULT 1,
    detail_kind TEXT,
    detail_url TEXT,
    detail_done INTEGER DEFAULT 0,
    score REAL DEFAULT 0,
    score_reasons TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active, score);

CREATE TABLE IF NOT EXISTS user_state (
    job_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,        -- saved | applied | interview | offer | rejected | hidden
    notes TEXT DEFAULT '',
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started TEXT, finished TEXT,
    raw_total INTEGER DEFAULT 0, india_total INTEGER DEFAULT 0,
    new_jobs INTEGER DEFAULT 0, closed_jobs INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS company_runs (
    run_id INTEGER, company TEXT, ats TEXT,
    ok INTEGER, raw_count INTEGER, india_count INTEGER,
    error TEXT, seconds REAL, ts TEXT
);
CREATE INDEX IF NOT EXISTS idx_company_runs ON company_runs(company, run_id);

-- Cached AmbitionBox lookups, hits and misses alike.
CREATE TABLE IF NOT EXISTS portal_pay (
    company TEXT, designation TEXT, data TEXT, fetched_at TEXT,
    PRIMARY KEY (company, designation)
);
"""

# Added after the first release; created on connect if an older database lacks them.
EXTRA_COLUMNS = {
    "pay_verdict": "TEXT DEFAULT 'unknown'",
    "est_min_lpa": "REAL", "est_max_lpa": "REAL",       # Claude's estimate
    "brain_flag": "TEXT", "brain_note": "TEXT", "brain_done": "INTEGER DEFAULT 0",
    # where the estimate came from: 'ambitionbox', 'claude' or 'band' (rough tier table)
    "est_source": "TEXT", "est_note": "TEXT", "est_url": "TEXT",
}

JOB_COLUMNS = [
    "id", "company", "title", "location", "cities", "is_remote", "scope",
    "employment_type", "level", "role", "is_tech", "exp_min", "exp_max",
    "salary_min_lpa", "salary_max_lpa", "salary_text", "description", "departments",
    "apply_url", "source", "posted_at", "detail_kind", "detail_url", "detail_done",
    "score", "score_reasons", "pay_verdict", "est_min_lpa", "est_max_lpa", "est_source",
]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_READY: set[str] = set()


def _starts_word(text: str | None, term: str) -> bool:
    """True if `term` begins a word in `text`: "uber" matches "Uber" and "Uber Eats"
    but not "Kubernetes"; "soft" still matches "Software"."""
    return bool(text) and re.search(r"(?<![a-z0-9])" + re.escape(term.lower()), text.lower()) is not None


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.create_function("starts_word", 2, _starts_word, deterministic=True)
    if str(path) in _READY:          # schema checks run once per process, not per request
        return conn
    conn.executescript(SCHEMA)
    have = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    for column, kind in EXTRA_COLUMNS.items():
        if column not in have:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {kind}")
    # One table row per company, title and level. Stored as an indexed generated
    # column because the list and every filter count group by it.
    if "grp" not in {r["name"] for r in conn.execute("PRAGMA table_xinfo(jobs)")}:
        conn.execute("ALTER TABLE jobs ADD COLUMN grp TEXT GENERATED ALWAYS AS "
                     "(company || '|' || lower(title) || '|' || level) VIRTUAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_grp ON jobs(is_active, grp)")
    _READY.add(str(path))
    return conn


def upsert_jobs(conn: sqlite3.Connection, jobs: list[dict], seen_at: str) -> int:
    """Insert or refresh jobs. Returns how many were new."""
    existing = {
        r["id"]: r["detail_done"]
        for r in conn.execute("SELECT id, detail_done FROM jobs")
    }
    # Estimates from AmbitionBox or Claude outlive a re-fetch of the listing.
    estimated = {
        r["id"] for r in conn.execute(
            "SELECT id FROM jobs WHERE est_source IN ('ambitionbox', 'claude', 'market')")
    }
    new = 0
    for job in jobs:
        row = dict(job)
        row["cities"] = json.dumps(row.get("cities") or [])
        row["score_reasons"] = json.dumps(row.get("score_reasons") or [])
        if row["id"] in existing:
            # A listing-only refresh must not wipe a description fetched earlier.
            keep_detail = existing[row["id"]] and not row.get("detail_done")
            cols = [
                c for c in JOB_COLUMNS
                if c != "id" and not (keep_detail and c in _DETAIL_OWNED)
                and not (row["id"] in estimated and c in _ESTIMATE_OWNED)
            ]
            conn.execute(
                f"UPDATE jobs SET {', '.join(f'{c}=:{c}' for c in cols)}, "
                "last_seen=:seen, is_active=1 WHERE id=:id",
                {**{c: row.get(c) for c in JOB_COLUMNS}, "seen": seen_at},
            )
        else:
            new += 1
            conn.execute(
                f"INSERT INTO jobs ({', '.join(JOB_COLUMNS)}, first_seen, last_seen, is_active) "
                f"VALUES ({', '.join(':' + c for c in JOB_COLUMNS)}, :seen, :seen, 1)",
                {**{c: row.get(c) for c in JOB_COLUMNS}, "seen": seen_at},
            )
    conn.commit()
    return new


# Fields the detail page fills in; a later listing-only pass leaves them alone.
_DETAIL_OWNED = {
    "description", "detail_done", "exp_min", "exp_max", "salary_min_lpa",
    "salary_max_lpa", "salary_text", "level", "employment_type", "location",
    "cities", "is_remote", "scope", "posted_at", "score", "score_reasons", "pay_verdict",
    # the estimate depends on the level, which the detail page decides
    "est_min_lpa", "est_max_lpa", "est_source",
}


_ESTIMATE_OWNED = {"est_min_lpa", "est_max_lpa", "est_source", "pay_verdict", "score",
                   "score_reasons"}


def close_missing(conn: sqlite3.Connection, company: str, seen_at: str) -> int:
    cur = conn.execute(
        "UPDATE jobs SET is_active=0 WHERE company=? AND is_active=1 AND last_seen<?",
        (company, seen_at),
    )
    return cur.rowcount


def previous_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """India job count per company from its most recent successful run."""
    rows = conn.execute(
        "SELECT company, india_count FROM company_runs c WHERE ok=1 AND run_id=("
        "SELECT MAX(run_id) FROM company_runs WHERE company=c.company AND ok=1)"
    )
    return {r["company"]: r["india_count"] for r in rows}


def job_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["cities"] = json.loads(d.get("cities") or "[]")
    d["score_reasons"] = json.loads(d.get("score_reasons") or "[]")
    for key in ("is_remote", "is_tech", "is_active", "detail_done"):
        if key in d:
            d[key] = bool(d[key])
    return d
