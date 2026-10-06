"""FastAPI app: job search API, application tracker, coverage report, refresh."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, pipeline, score

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
STATUSES = {"saved", "applied", "interview", "offer", "rejected", "hidden"}

app = FastAPI(title="Job Finder")
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def cache_assets(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        # File names carry a content hash, so they can be cached for good.
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response

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


def _multi(value: str | None) -> list[str]:
    return [v for v in (value or "").split(",") if v]


def _where(
    q, role, level, etype, city, company, source, status, remote, tech, salary_min,
    exp_max, has_salary, new_days, pay_filter, hide_bad, min_score, has_description,
    posted_days=None,
) -> tuple[str, list]:
    clauses, args = ["j.is_active = 1"], []

    def any_of(column: str, values: list[str]) -> None:
        if values:
            clauses.append(f"{column} IN ({','.join('?' * len(values))})")
            args.extend(values)

    any_of("j.role", _multi(role))
    any_of("j.level", _multi(level))
    any_of("j.employment_type", _multi(etype))
    any_of("j.company", _multi(company))
    any_of("j.source", _multi(source))
    any_of("j.pay_verdict", _multi(pay_filter))
    if hide_bad and not _multi(pay_filter):
        clauses.append("j.pay_verdict NOT IN ('low', 'unpaid', 'suspicious')")
    if min_score:
        clauses.append("j.score >= ?")
        args.append(min_score)
    if has_description:
        clauses.append("j.description != ''")

    cities = _multi(city)
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
        clauses.append("j.first_seen >= datetime('now', ?)")
        args.append(f"-{int(new_days)} days")

    statuses = _multi(status)
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
    return " AND ".join(clauses), args


@app.get("/api/jobs")
def list_jobs(
    q: str | None = None, role: str | None = None, level: str | None = None,
    type: str | None = None, city: str | None = None, company: str | None = None,
    source: str | None = None, status: str | None = None,
    remote: bool = False, tech: bool = False, has_salary: bool = False,
    salary_min: float | None = None, exp_max: float | None = None,
    new_days: int | None = None, pay: str | None = None, hide_bad: bool = False,
    min_score: float | None = None, has_description: bool = False,
    posted_days: int | None = None, sort: str = "score", dir: str | None = None,
    page: int = Query(1, ge=1), size: int = Query(30, ge=1, le=200),
):
    where, args = _where(q, role, level, type, city, company, source, status, remote, tech,
                         salary_min, exp_max, has_salary, new_days, pay, hide_bad, min_score,
                         has_description, posted_days)
    base = f"FROM jobs j LEFT JOIN user_state u ON u.job_id = j.id WHERE {where}"
    conn = db.connect()
    try:
        # One row per company + title + level: the same role posted for several
        # cities or requisitions is shown once, with a count. The representative
        # is a tracked posting if there is one, otherwise the best-scoring.
        group = "GROUP BY j.grp"
        total = conn.execute(f"SELECT COUNT(*) FROM (SELECT 1 {base} {group})", args).fetchone()[0]
        order = order_by(sort, dir)
        if q and sort == "score" and dir != "asc":
            order = "starts_word(j.company, ?) DESC, " + order      # company matches first
            args = [*args, q.split()[0]]
        rows = conn.execute(
            f"SELECT {LIST_COLUMNS}, COUNT(*) AS openings, "
            "MAX((u.status IS NOT NULL AND u.status != 'hidden') * 1000 + j.score) AS pick "
            f"{base} {group} ORDER BY {order} LIMIT ? OFFSET ?",
            [*args, size, (page - 1) * size],
        ).fetchall()
        return {"total": total, "page": page, "size": size,
                "jobs": [db.job_to_dict(r) for r in rows]}
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT j.*, u.status AS status, u.notes AS notes FROM jobs j "
            "LEFT JOIN user_state u ON u.job_id = j.id WHERE j.id = ?", (job_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "job not found")
        job = db.job_to_dict(row)
        job["others"] = [dict(r) for r in conn.execute(
            "SELECT id, location, apply_url FROM jobs WHERE is_active=1 AND company=? "
            "AND lower(title)=lower(?) AND level=? AND id != ? ORDER BY location LIMIT 40",
            (job["company"], job["title"], job["level"], job_id),
        )]
        return job
    finally:
        conn.close()


class StateIn(BaseModel):
    status: str | None = None
    notes: str | None = None


@app.put("/api/jobs/{job_id}/state")
def set_state(job_id: str, body: StateIn):
    if body.status is not None and body.status not in STATUSES | {""}:
        raise HTTPException(400, f"status must be one of {sorted(STATUSES)}")
    conn = db.connect()
    try:
        if body.status == "hidden":
            # Dismissing a row dismisses every posting it stands for.
            conn.execute(
                "INSERT INTO user_state (job_id, status, notes, updated_at) "
                "SELECT o.id, 'hidden', '', ? FROM jobs j JOIN jobs o ON o.company = j.company "
                "AND lower(o.title) = lower(j.title) AND o.level = j.level WHERE j.id = ? "
                "ON CONFLICT(job_id) DO UPDATE SET status='hidden', updated_at=excluded.updated_at",
                (db.now(), job_id),
            )
        elif body.status == "":
            conn.execute("DELETE FROM user_state WHERE job_id = ?", (job_id,))
        else:
            current = conn.execute(
                "SELECT status, notes FROM user_state WHERE job_id = ?", (job_id,)
            ).fetchone()
            status = body.status or (current["status"] if current else "saved")
            notes = body.notes if body.notes is not None else (current["notes"] if current else "")
            conn.execute(
                "INSERT INTO user_state (job_id, status, notes, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, "
                "notes=excluded.notes, updated_at=excluded.updated_at",
                (job_id, status, notes, db.now()),
            )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.get("/api/facets")
def facets(
    q: str | None = None, role: str | None = None, level: str | None = None,
    type: str | None = None, city: str | None = None, company: str | None = None,
    source: str | None = None, status: str | None = None,
    remote: bool = False, tech: bool = False, has_salary: bool = False,
    salary_min: float | None = None, exp_max: float | None = None,
    new_days: int | None = None, pay: str | None = None, hide_bad: bool = False,
    min_score: float | None = None, has_description: bool = False,
    posted_days: int | None = None,
):
    """Counts for every filter menu, given the other filters currently applied.

    Each menu is counted with its own selection removed, so the number beside an
    option is how many rows you would get by ticking it. Counts are of rows as
    the table shows them (one per company, title and level).
    """
    # Fetch the rows that pass every non-menu filter once, then count each menu in
    # Python with its own selection left out. One query instead of one per menu.
    where, args = _where(
        q=q, role=None, level=None, etype=None, city=None, company=None, source=None,
        status=status, remote=remote, tech=tech, salary_min=salary_min, exp_max=exp_max,
        has_salary=has_salary, new_days=None, pay_filter=None, hide_bad=False,
        min_score=min_score, has_description=has_description, posted_days=posted_days,
    )
    picked = {
        "role": set(_multi(role)), "level": set(_multi(level)), "type": set(_multi(type)),
        "company": set(_multi(company)), "source": set(_multi(source)),
        "pay": set(_multi(pay)), "city": set(_multi(city)),
    }
    hidden_pay = {"low", "unpaid", "suspicious"} if hide_bad else set()
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT j.grp, j.role, j.level, j.employment_type AS type, j.company, j.source, "
            "j.pay_verdict AS pay, j.cities, j.first_seen >= datetime('now', '-1 day') AS is_new, "
            + ("j.first_seen >= datetime('now', ?) AS in_window " if new_days else "1 AS in_window ")
            + f"FROM jobs j LEFT JOIN user_state u ON u.job_id = j.id WHERE {where}",
            ([f"-{int(new_days)} days"] if new_days else []) + args,
        ).fetchall()

        groups: dict[str, dict[str, set]] = {name: {} for name in picked}
        all_rows: set = set()
        new_rows: set = set()
        for r in rows:
            cities = json.loads(r["cities"]) if r["cities"] != "[]" else []
            ok = {
                name: (not chosen or r[name] in chosen)
                for name, chosen in picked.items() if name not in ("city", "pay")
            }
            ok["city"] = not picked["city"] or any(c in picked["city"] for c in cities)
            # With no pay option ticked, "hide low-pay" decides; ticking one overrides it.
            ok["pay"] = (r["pay"] in picked["pay"]) if picked["pay"] else (r["pay"] not in hidden_pay)
            failed = [name for name, passed in ok.items() if not passed]
            if not failed:
                all_rows.add(r["grp"])
                if r["is_new"]:
                    new_rows.add(r["grp"])
            if not r["in_window"]:
                continue
            for name in picked:
                # A row counts toward a menu if that menu is the only thing excluding it.
                if failed and failed != [name]:
                    continue
                for value in (cities if name == "city" else [r[name]]):
                    if value:
                        groups[name].setdefault(value, set()).add(r["grp"])

        def counts(name: str) -> list[dict]:
            ordered = sorted(groups[name].items(), key=lambda kv: -len(kv[1]))[:400]
            return [{"value": value, "count": len(members)} for value, members in ordered]

        tracker = {
            r["status"]: r["n"] for r in conn.execute(
                "SELECT u.status, COUNT(*) AS n FROM user_state u JOIN jobs j ON j.id = u.job_id "
                "WHERE j.is_active = 1 GROUP BY 1")
        }
        totals = conn.execute(
            "SELECT COUNT(*) AS jobs, COUNT(DISTINCT company) AS companies, "
            "SUM(is_tech) AS tech, SUM(salary_text != '') AS with_salary, "
            "SUM(description != '') AS with_description, "
            "SUM(first_seen >= datetime('now', '-1 day')) AS new_today "
            "FROM jobs WHERE is_active = 1"
        ).fetchone()
        return {
            "totals": dict(totals), "tracker": tracker,
            "rows": {"all": len(all_rows), "new": len(new_rows)},
            "role": counts("role"), "level": counts("level"), "type": counts("type"),
            "company": counts("company"), "source": counts("source"), "pay": counts("pay"),
            "city": counts("city"),
        }
    finally:
        conn.close()


@app.get("/api/coverage")
def coverage():
    """Per-company result of the latest run, plus companies with no scraper."""
    conn = db.connect()
    try:
        last = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not last:
            return {"run": None, "companies": [], "summary": {}}
        previous = {
            r["company"]: r["india_count"] for r in conn.execute(
                "SELECT company, india_count FROM company_runs c WHERE ok = 1 AND run_id = ("
                "SELECT MAX(run_id) FROM company_runs WHERE company = c.company AND ok = 1 "
                "AND run_id < ?)", (last["id"],))
        }
        companies = []
        for r in conn.execute(
            "SELECT * FROM company_runs WHERE run_id = ? ORDER BY india_count DESC", (last["id"],)
        ):
            prev = previous.get(r["company"])
            status = pipeline.health_status(bool(r["ok"]), r["raw_count"], r["india_count"], prev)
            if r["ats"] == "custom":
                status = "manual"
            companies.append({
                "company": r["company"], "ats": r["ats"], "status": status,
                "raw": r["raw_count"], "india": r["india_count"], "previous": prev,
                "error": r["error"], "seconds": r["seconds"],
            })
        summary: dict[str, int] = {}
        for c in companies:
            summary[c["status"]] = summary.get(c["status"], 0) + 1
        return {"run": dict(last), "companies": companies, "summary": summary}
    finally:
        conn.close()


_refresh_task: asyncio.Task | None = None


@app.post("/api/refresh")
async def refresh():
    global _refresh_task
    if pipeline.PROGRESS["running"]:
        return {"started": False, "progress": pipeline.PROGRESS}
    _refresh_task = asyncio.create_task(pipeline.run())
    return {"started": True}


@app.get("/api/refresh")
def refresh_status():
    return pipeline.PROGRESS


class PromptIn(BaseModel):
    job_ids: list[str]


@app.post("/api/prompt")
def claude_prompt(body: PromptIn):
    """A prompt to paste into Claude with your profile and the chosen jobs."""
    if not body.job_ids:
        raise HTTPException(400, "no jobs selected")
    conn = db.connect()
    try:
        marks = ",".join("?" * len(body.job_ids))
        rows = conn.execute(f"SELECT * FROM jobs WHERE id IN ({marks})", body.job_ids).fetchall()
    finally:
        conn.close()
    profile = score.load_profile()["raw"]
    keep = {k: profile.get(k) for k in ("education", "skills", "experience", "projects", "job_preferences")}
    blocks = []
    for i, row in enumerate(rows, 1):
        job = db.job_to_dict(row)
        blocks.append(
            f"### Job {i}: {job['title']} at {job['company']}\n"
            f"Location: {job['location']}\nLevel: {job['level']} | Type: {job['employment_type']}"
            f" | Salary: {job['salary_text'] or 'not stated'}\nApply: {job['apply_url']}\n\n"
            f"{(job['description'] or 'No description available.')[:3500]}"
        )
    prompt = (
        "You are helping me decide which jobs to apply to first and how to tailor each "
        "application.\n\n## My profile\n```json\n"
        + json.dumps(keep, indent=2, ensure_ascii=False)
        + "\n```\n\n## Jobs\n\n" + "\n\n---\n\n".join(blocks)
        + "\n\n## What I need\n"
        "1. Rank these jobs from best to worst fit for me, with a fit score out of 10 and "
        "one line on why.\n"
        "2. Flag any job I am clearly not eligible for (experience, graduation year, location).\n"
        "3. For the top 3, list the resume bullet points I should lead with and the gaps I "
        "should address in a cover note.\n"
        "4. For the top 3, write a 4-line referral request I can send on LinkedIn.\n"
    )
    return {"prompt": prompt, "jobs": len(rows)}


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        target = WEB_DIST / path
        if path and target.is_file() and WEB_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")
