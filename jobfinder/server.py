"""FastAPI app: job search API, application tracker, coverage report, refresh."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, pipeline, queries, score
from .pay import floors as pay_floors

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
    where, args = queries.build_where(
        q, role, level, type, city, company, source, status, remote, tech, salary_min,
        exp_max, has_salary, new_days, pay, hide_bad, min_score, has_description, posted_days)
    conn = db.connect()
    try:
        total, rows = queries.find_jobs(conn, where, args, q, sort, dir, page, size)
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
        if not conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(404, "job not found")
        if body.status == "hidden":
            # Dismissing a row dismisses every posting it stands for.
            conn.execute(
                "INSERT INTO user_state (job_id, status, notes, updated_at) "
                "SELECT o.id, 'hidden', '', ? FROM jobs j JOIN jobs o ON o.company = j.company "
                "AND lower(o.title) = lower(j.title) AND o.level = j.level WHERE j.id = ? "
                "ON CONFLICT(job_id) DO UPDATE SET status='hidden', updated_at=excluded.updated_at",
                (db.now(), job_id),
            )
        else:
            current = conn.execute(
                "SELECT status, notes FROM user_state WHERE job_id = ?", (job_id,)
            ).fetchone()
            notes = body.notes if body.notes is not None else (current["notes"] if current else "")
            if body.status is not None:
                status = body.status
            elif current:
                status = current["status"]
            else:
                status = "saved" if notes else ""       # a first note shortlists the job
            if status or notes:
                # Clearing the status of a job with a note keeps the note: the row
                # stays with an empty status rather than taking the note with it.
                conn.execute(
                    "INSERT INTO user_state (job_id, status, notes, updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, "
                    "notes=excluded.notes, updated_at=excluded.updated_at",
                    (job_id, status, notes, db.now()),
                )
            else:
                conn.execute("DELETE FROM user_state WHERE job_id = ?", (job_id,))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


class PayFloorsIn(BaseModel):
    min_lpa: float
    target_lpa: float


@app.get("/api/settings/pay")
def get_pay_floors():
    floors = pay_floors(score.load_profile())
    return {"min_lpa": floors["min_lpa"], "target_lpa": floors["target_lpa"]}


@app.put("/api/settings/pay")
def set_pay_floors(body: PayFloorsIn):
    """Change the pay floors in user_profile.yaml, then re-score every job in the background.

    Re-scoring 20,000+ jobs takes over a minute, too long to hold a request open. It reports
    through the same progress record as a refresh, so the app shows it and reloads at the end.
    """
    if pipeline.PROGRESS["running"]:
        # A refresh re-scores as it goes; two writers would leave a mix of old and new floors.
        raise HTTPException(409, "a refresh or re-score is running: save when it ends")
    try:
        score.save_pay_floors(body.min_lpa, body.target_lpa)
    except ValueError as error:
        raise HTTPException(400, str(error))
    pipeline.PROGRESS.update(running=True, done=0, total=0, current="re-scoring")
    threading.Thread(target=_rescore_in_background, name="rescore", daemon=True).start()
    return {**get_pay_floors(), "rescoring": True}


def _rescore_in_background() -> None:
    conn = db.connect()
    try:
        pipeline.rescore(conn)
    finally:
        conn.close()
        pipeline.PROGRESS.update(running=False, current="")


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
    where, args = queries.build_where(
        q=q, role=None, level=None, etype=None, city=None, company=None, source=None,
        status=status, remote=remote, tech=tech, salary_min=salary_min, exp_max=exp_max,
        has_salary=has_salary, new_days=None, pay_filter=None, hide_bad=False,
        min_score=min_score, has_description=has_description, posted_days=posted_days,
    )
    picked = {
        "role": set(queries.multi(role)), "level": set(queries.multi(level)),
        "type": set(queries.multi(type)), "company": set(queries.multi(company)),
        "source": set(queries.multi(source)), "pay": set(queries.multi(pay)),
        "city": set(queries.multi(city)),
    }
    hidden_pay = {"low", "unpaid", "suspicious"} if hide_bad else set()
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT j.grp, j.role, j.level, j.employment_type AS type, j.company, j.source, "
            f"j.pay_verdict AS pay, j.cities, j.first_seen >= {queries.NEW_SINCE} AS is_new, "
            + (f"j.first_seen >= {db.ago()} AS in_window " if new_days else "1 AS in_window ")
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
                # "First seen within" narrows the table, so it narrows the All count too.
                if r["in_window"]:
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
                "WHERE j.is_active = 1 AND u.status != '' GROUP BY 1")
        }
        totals = conn.execute(
            "SELECT COUNT(*) AS jobs, COUNT(DISTINCT company) AS companies, "
            "SUM(is_tech) AS tech, SUM(salary_text != '') AS with_salary, "
            "SUM(description != '') AS with_description, "
            f"SUM(first_seen >= {queries.NEW_SINCE}) AS new_today "
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
    """Each company's most recent fetch result, plus companies with no scraper."""
    conn = db.connect()
    try:
        # Only companies still in companies.yaml: one taken off the list is no longer fetched.
        tracked = {c["name"] for c in pipeline.load_companies()}
        rows = [r for r in db.latest_company_runs(conn) if r["company"] in tracked]
        if not rows:
            return {"run": None, "companies": [], "summary": {}}
        last = conn.execute(
            "SELECT * FROM runs WHERE id = (SELECT MAX(run_id) FROM company_runs)").fetchone()
        # What each company returned the last time it was fetched successfully before that.
        previous = {
            r["company"]: r["india_count"] for r in conn.execute(
                "SELECT company, india_count FROM company_runs c WHERE ok = 1 AND run_id = ("
                "SELECT MAX(run_id) FROM company_runs WHERE company = c.company AND ok = 1 "
                "AND run_id < (SELECT MAX(run_id) FROM company_runs WHERE company = c.company))")
        }
        companies = []
        for r in rows:
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


@app.post("/api/refresh")
async def refresh():
    if pipeline.PROGRESS["running"]:
        return {"started": False, "progress": pipeline.PROGRESS}
    # Claimed here, before the run gets going, so a second click cannot start another.
    pipeline.PROGRESS.update(running=True, done=0, total=0, current="")
    # On its own thread with its own event loop. A run spends long stretches parsing
    # and scoring; on the server's loop that froze the whole app until it was done.
    threading.Thread(target=lambda: asyncio.run(pipeline.run()), name="refresh", daemon=True).start()
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
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "not found")       # a mistyped API path is not the web app
        target = WEB_DIST / path
        if path and target.is_file() and WEB_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")
