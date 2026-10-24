"""Job queries shared by the web API and the agent's tools: filters, sorting, the grouped list.

One copy of this code means the job table and the agent can never disagree about which
jobs match a filter.
"""

from __future__ import annotations

import sqlite3

from . import db

LIST_COLUMNS = (
    "j.id, j.company, j.title, j.location, j.cities, j.is_remote, j.scope, "
    "j.employment_type, j.level, j.role, j.is_tech, j.exp_min, j.exp_max, "
    "j.salary_min_lpa, j.salary_max_lpa, j.salary_text, j.apply_url, j.source, "
    "j.posted_at, j.first_seen, j.score, j.pay_verdict, "
    "j.est_min_lpa, j.est_max_lpa, j.est_source, j.est_note, j.est_url, j.brain_note, "
    "u.status AS status"
)

# Sortable columns: SQL expression, and the direction a first click gives.
# Rows with no value for the column always go last, whichever way it is sorted.
PAY_LOW = "COALESCE(j.salary_min_lpa, j.est_min_lpa)"
STATUS_RANK = ("CASE u.status WHEN 'offer' THEN 1 WHEN 'interview' THEN 2 WHEN 'applied' THEN 3 "
               "WHEN 'saved' THEN 4 WHEN 'rejected' THEN 5 END")
# The Location column shows the canonical city list when there is one, so sort by that.
PLACE = ("NULLIF(CASE WHEN j.cities != '[]' THEN replace(replace(replace(j.cities, '[\"', ''), "
         "'\"]', ''), '\", \"', ', ') ELSE j.location END, '')")
SORTS = {
    "score": ("j.score", "desc"),
    "company": ("j.company COLLATE NOCASE", "asc"),
    "title": ("j.title COLLATE NOCASE", "asc"),
    "location": (PLACE + " COLLATE NOCASE", "asc"),
    "pay": (PAY_LOW, "desc"),
    "posted": ("NULLIF(j.posted_at, '')", "desc"),
    "source": ("j.source", "asc"),
    "status": (STATUS_RANK, "asc"),
}
SORT_ALIASES = {"newest": "posted", "salary": "pay"}


def order_by(sort: str, direction: str | None) -> str:
    key = SORT_ALIASES.get(sort, sort)
    expr, default = SORTS.get(key, SORTS["score"])
    way = direction if direction in ("asc", "desc") else default
    # j.score then j.id break ties, so paging never repeats or skips a row.
    return f"({expr}) IS NULL, {expr} {way.upper()}, j.score DESC, j.id"


POSTED = "COALESCE(NULLIF(j.posted_at, ''), substr(j.first_seen, 1, 10))"
NEW_SINCE = db.ago("'-1 day'")      # "new" means first seen in the last 24 hours


def multi(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


def build_where(
    q, role, level, etype, city, company, source, status, remote, tech, salary_min,
    exp_max, has_salary, new_days, pay_filter, hide_bad, min_score, has_description,
    posted_days=None, desc=None,
) -> tuple[str, list]:
    clauses, args = ["j.is_active = 1"], []

    def any_of(column: str, values: list[str]) -> None:
        if values:
            clauses.append(f"{column} IN ({','.join('?' * len(values))})")
            args.extend(values)

    any_of("j.role", multi(role))
    any_of("j.level", multi(level))
    any_of("j.employment_type", multi(etype))
    any_of("j.company", multi(company))
    any_of("j.source", multi(source))
    any_of("j.pay_verdict", multi(pay_filter))
    if hide_bad and not multi(pay_filter):
        clauses.append("j.pay_verdict NOT IN ('low', 'unpaid', 'suspicious')")
    if min_score:
        clauses.append("j.score >= ?")
        args.append(min_score)
    if has_description:
        clauses.append("j.description != ''")

    cities = multi(city)
    if cities:
        clauses.append("(" + " OR ".join("j.cities LIKE ?" for _ in cities) + ")")
        args.extend(f'%"{c}"%' for c in cities)
    if remote:
        clauses.append("j.is_remote = 1")
    if tech:
        clauses.append("j.is_tech = 1")
    if has_salary:
        clauses.append("j.salary_text != ''")
    if salary_min is not None:
        # Stated pay, or the estimate where the posting states none.
        # The low end of the range must clear the bar: "at least 12" should not
        # return a 6-14 LPA job just because its top end reaches 12.
        clauses.append("COALESCE(j.salary_min_lpa, j.est_min_lpa) >= ?")
        args.append(salary_min)
    if exp_max is not None:
        # Jobs that do not state experience are kept: dropping them would hide
        # most postings, and the level filter is the better tool for those.
        clauses.append("(j.exp_min IS NULL OR j.exp_min <= ?)")
        args.append(exp_max)
    if posted_days:
        # The posting's own date; sources that give none fall back to when we first saw it.
        clauses.append(f"{POSTED} >= date('now', ?)")
        args.append(f"-{int(posted_days)} days")
    if new_days:
        clauses.append(f"j.first_seen >= {db.ago()}")
        args.append(f"-{int(new_days)} days")

    statuses = multi(status)
    if statuses:
        any_of("u.status", statuses)
    else:
        clauses.append("(u.status IS NULL OR u.status != 'hidden')")

    # Search matches the title, company and place only. Matching descriptions too
    # made a search for "amazon" return every posting that mentions AWS.
    # Terms match from the start of a word, so "uber" does not match "Kubernetes".
    for term in (q or "").split():
        clauses.append("(starts_word(j.company, ?) OR starts_word(j.title, ?) OR starts_word(j.location, ?))")
        args.extend([term] * 3)
    # Words the description must contain, each matched from the start of a word like the
    # search above. Used by the agent: "mentions Kubernetes" has no menu in the table.
    # LIKE runs in C and drops most rows first, so the Python check only sees candidates:
    # about 4 s down to about 1 s over 20,000 descriptions. (LIKE ignores case for ASCII only.)
    for term in (desc or "").split():
        clauses.append("(j.description LIKE ? AND starts_word(j.description, ?))")
        args.extend([f"%{term}%", term])
    return " AND ".join(clauses), args


def find_jobs(
    conn: sqlite3.Connection, where: str, args: list, q: str | None,
    sort: str, direction: str | None, page: int, size: int,
) -> tuple[int, list[sqlite3.Row]]:
    """The grouped, sorted list behind the job table: (total groups, rows for this page)."""
    base = f"FROM jobs j LEFT JOIN user_state u ON u.job_id = j.id WHERE {where}"
    # One row per company + title + level: the same role posted for several
    # cities or requisitions is shown once, with a count. The representative
    # is a tracked posting if there is one, otherwise the best-scoring.
    group = "GROUP BY j.grp"
    total = conn.execute(f"SELECT COUNT(*) FROM (SELECT 1 {base} {group})", args).fetchone()[0]
    order = order_by(sort, direction)
    terms = (q or "").split()        # a search of only spaces has no terms
    if terms and sort == "score" and direction != "asc":
        order = "starts_word(j.company, ?) DESC, " + order      # company matches first
        args = [*args, terms[0]]
    rows = conn.execute(
        f"SELECT {LIST_COLUMNS}, COUNT(*) AS openings, "
        "MAX((u.status IS NOT NULL AND u.status != 'hidden') * 1000 + j.score) AS pick "
        f"{base} {group} ORDER BY {order} LIMIT ? OFFSET ?",
        [*args, size, (page - 1) * size],
    ).fetchall()
    return total, rows
