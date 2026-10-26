"""SQLite store: jobs, your application status per job, and per-company run health."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import enrich

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
    status TEXT NOT NULL,        -- saved | applied | interview | offer | rejected | hidden,
                                 -- or '' for a job that only has a note
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

-- Every Ask run: what was asked, each step, what came back. Read when debugging an answer,
-- and real questions become eval cases.
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT, source TEXT,          -- app | cli | eval
    question TEXT, answer TEXT, stopped TEXT, job_ids TEXT,
    total_matching INTEGER, search TEXT, steps TEXT, models TEXT,
    tokens_in INTEGER, tokens_out INTEGER, seconds REAL
);

-- Every deep dive on a job: the checked report, what code dropped from it and why, the pages read.
CREATE TABLE IF NOT EXISTS deep_dives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT, created_at TEXT, stopped TEXT,
    report TEXT, dropped TEXT, pages TEXT, steps TEXT, models TEXT,
    tokens_in INTEGER, tokens_out INTEGER, seconds REAL
);
CREATE INDEX IF NOT EXISTS deep_dives_job ON deep_dives (job_id, id);

-- Coverage repair: a board the agent proposes for a broken company, proved by code (India jobs
-- counted), applied to companies.yaml only when the user approves it.
CREATE TABLE IF NOT EXISTS fix_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT, created_at TEXT, decided_at TEXT,
    status TEXT,                 -- pending | approved | rejected | rejected_by_check | no_fix
    last_fetch TEXT, current TEXT, proposed TEXT,
    india_jobs INTEGER, total_jobs INTEGER, sample_titles TEXT, evidence TEXT,
    steps TEXT, tokens INTEGER
);
"""

# Added after the first release; created on connect if an older database lacks them.
EXTRA_COLUMNS = {
    "pay_verdict": "TEXT DEFAULT 'unknown'",
    "est_min_lpa": "REAL", "est_max_lpa": "REAL",       # Claude's estimate
    "brain_flag": "TEXT", "brain_note": "TEXT", "brain_done": "INTEGER DEFAULT 0",
    # where the estimate came from: 'ambitionbox', 'claude' or 'band' (rough tier table)
    "est_source": "TEXT", "est_note": "TEXT", "est_url": "TEXT",
    # when a refresh first found the posting gone; cleared if it comes back
    "closed_at": "TEXT",
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


def ago(shift: str = "?") -> str:
    """SQL for the moment `shift` from now (a quoted modifier such as "'-1 day'", or
    ? to bind one), written the way now() stores timestamps.

    SQLite's own datetime() puts a space where these have a "T", so comparing a
    stored timestamp with it as text is wrong for the whole day of the cutoff.
    """
    return f"strftime('%Y-%m-%dT%H:%M:%SZ', 'now', {shift})"


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
    # Jobs closed before closed_at existed: the last time they were seen is the best guess.
    conn.execute("UPDATE jobs SET closed_at = last_seen WHERE is_active = 0 AND closed_at IS NULL")
    # One table row per group (enrich.group_key), indexed because the list and every
    # filter count group by it. It was once a generated column of the exact company,
    # title and level; SQLite cannot change one, so an old database is converted here.
    columns = {r["name"]: r["hidden"] for r in conn.execute("PRAGMA table_xinfo(jobs)")}
    if columns.get("grp") in (2, 3):                  # 2, 3: a generated column
        conn.execute("DROP INDEX IF EXISTS idx_jobs_grp")
        conn.execute("ALTER TABLE jobs DROP COLUMN grp")
        columns.pop("grp")
    if "grp" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN grp TEXT")
        refresh_groups(conn)
        conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_grp ON jobs(is_active, grp)")
    # The UPDATE above opens a transaction; left open it held the write lock for the life of the
    # connection. A deep dive keeps its connection for minutes, and every other process (the
    # app, the 07:00 fetch) then failed with "database is locked".
    conn.commit()
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
                "last_seen=:seen, is_active=1, closed_at=NULL WHERE id=:id",
                {**{c: row.get(c) for c in JOB_COLUMNS}, "seen": seen_at},
            )
        else:
            new += 1
            conn.execute(
                f"INSERT INTO jobs ({', '.join(JOB_COLUMNS)}, first_seen, last_seen, is_active) "
                f"VALUES ({', '.join(':' + c for c in JOB_COLUMNS)}, :seen, :seen, 1)",
                {**{c: row.get(c) for c in JOB_COLUMNS}, "seen": seen_at},
            )
    # From what is now stored: a listing refresh may have kept the detail page's level.
    refresh_groups(conn, [job["id"] for job in jobs])
    conn.commit()
    return new


def refresh_groups(conn: sqlite3.Connection, ids: list[str] | None = None) -> None:
    """Recompute grp, the table's one-row-per-job key, for these jobs (all when None)."""
    if ids is None:
        rows = conn.execute("SELECT id, company, title, level FROM jobs").fetchall()
    else:
        rows = []
        for start in range(0, len(ids), 500):          # stay under SQLite's variable limit
            chunk = ids[start:start + 500]
            rows += conn.execute(f"SELECT id, company, title, level FROM jobs WHERE id IN "
                                 f"({','.join('?' * len(chunk))})", chunk).fetchall()
    conn.executemany("UPDATE jobs SET grp = ? WHERE id = ?",
                     [(enrich.group_key(r[1], r[2], r[3]), r[0]) for r in rows])


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
        "UPDATE jobs SET is_active=0, closed_at=? WHERE company=? AND is_active=1 AND last_seen<?",
        (seen_at, company, seen_at),
    )
    return cur.rowcount


# A job someone tracked: a status other than dismissed, or a note.
TRACKED = "SELECT job_id FROM user_state WHERE status NOT IN ('', 'hidden') OR notes != ''"


def purge_closed(conn: sqlite3.Connection, aggregators: set[str], grace_days: int) -> int:
    """Delete closed jobs nobody tracked, once they have been closed for the grace period.

    A board can fail for a run and make its jobs look closed, so a company board's job
    waits grace_days, and one that comes back in that time simply reopens. An aggregator
    job was already unseen for two weeks before it was closed, so it goes at once.
    A dismissed job's user_state row stays, so a repost of it is still dismissed.
    """
    marks = ",".join("?" * len(aggregators))
    cur = conn.execute(
        f"DELETE FROM jobs WHERE is_active = 0 AND closed_at IS NOT NULL "
        f"AND (source IN ({marks}) OR closed_at < {ago()}) AND id NOT IN ({TRACKED})",
        (*sorted(aggregators), f"-{int(grace_days)} days"),
    )
    return cur.rowcount


def latest_company_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Each company's most recent fetch result, largest first.

    Not "the rows of the latest run": a run limited to some companies (`run --only`)
    or one cut short only has rows for those, and the rest keep their last result.
    """
    return conn.execute(
        "SELECT * FROM company_runs c WHERE run_id = ("
        "SELECT MAX(run_id) FROM company_runs WHERE company = c.company) "
        "ORDER BY india_count DESC"
    ).fetchall()


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
