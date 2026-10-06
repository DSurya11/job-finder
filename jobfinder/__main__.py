"""Command line entry point: python -m jobfinder <command>."""

from __future__ import annotations

import argparse
import asyncio
import logging


def main() -> None:
    ap = argparse.ArgumentParser(prog="jobfinder", description="India job aggregator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="fetch all companies and update the database")
    run.add_argument("--only", help="comma-separated company names or ATS types")
    run.add_argument("--no-details", action="store_true", help="skip the description pass")
    run.add_argument("-v", "--verbose", action="store_true")

    serve = sub.add_parser("serve", help="start the web app")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--host", default="127.0.0.1")

    disc = sub.add_parser("discover", help="find job boards for the companies in a seed file")
    disc.add_argument("seeds")
    disc.add_argument("--write", action="store_true", help="merge results into companies.yaml")

    brain = sub.add_parser("brain", help="have Claude estimate pay and flag fake jobs (needs ANTHROPIC_API_KEY)")
    brain.add_argument("--limit", type=int, default=300, help="most jobs to assess this run")

    portal = sub.add_parser("pay", help="look up pay on AmbitionBox for jobs that do not state it")
    portal.add_argument("--limit", type=int, default=300, help="most salary pages to request this run")

    sub.add_parser("rescore", help="re-score stored jobs after editing user_profile.yaml")
    sub.add_parser("health", help="show companies whose last fetch looks wrong")

    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s", datefmt="%H:%M:%S",
    )

    if args.cmd == "run":
        from . import pipeline
        companies = pipeline.load_companies()
        if args.only:
            wanted = {w.strip().lower() for w in args.only.split(",")}
            companies = [c for c in companies
                         if c["name"].lower() in wanted or c.get("ats", "").lower() in wanted]
        summary = asyncio.run(pipeline.run(companies, with_details=not args.no_details))
        pipeline.print_summary(summary)
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("jobfinder.server:app", host=args.host, port=args.port)
    elif args.cmd == "discover":
        from .discover import discover
        asyncio.run(discover(args.seeds, write=args.write))
    elif args.cmd == "pay":
        from . import portal as portal_module
        print(asyncio.run(portal_module.run(args.limit)))
    elif args.cmd == "brain":
        from . import brain as brain_module
        print(brain_module.run(args.limit))
    elif args.cmd == "rescore":
        from . import db, pay, score
        conn = db.connect()
        profile = score.load_profile()
        import json
        rows = conn.execute("SELECT * FROM jobs").fetchall()
        for row in rows:
            job = db.job_to_dict(row)
            pay.apply_band(job)
            job["pay_verdict"] = pay.judge(job, profile)
            value, reasons = score.score_job(job, profile)
            conn.execute(
                "UPDATE jobs SET score=?, score_reasons=?, pay_verdict=?, est_min_lpa=?, "
                "est_max_lpa=?, est_source=? WHERE id=?",
                (value, json.dumps(reasons), job["pay_verdict"], job.get("est_min_lpa"),
                 job.get("est_max_lpa"), job.get("est_source"), job["id"]))
        conn.commit()
        print(f"Re-scored {len(rows)} jobs")
    elif args.cmd == "health":
        from . import db, pipeline
        conn = db.connect()
        last = conn.execute("SELECT MAX(run_id) AS r FROM company_runs").fetchone()["r"]
        rows = conn.execute("SELECT * FROM company_runs WHERE run_id=? ORDER BY india_count", (last,))
        for r in rows:
            status = pipeline.health_status(bool(r["ok"]), r["raw_count"], r["india_count"], None)
            if status != "ok":
                print(f"[{status:6}] {r['company']:28} {r['ats']:16} {r['error'] or '0 postings'}")


if __name__ == "__main__":
    main()
