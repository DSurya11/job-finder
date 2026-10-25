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

    portal = sub.add_parser("pay", help="look up pay on AmbitionBox for jobs that do not state it")
    portal.add_argument("--limit", type=int, default=300, help="most salary pages to request this run")

    sub.add_parser("rescore", help="re-score stored jobs after editing user_profile.yaml")
    sub.add_parser("health", help="show companies whose last fetch looks wrong")
    ask = sub.add_parser("ask", help="ask the agent a question about your jobs, and see every step")
    ask.add_argument("question")
    ask.add_argument("--max-steps", type=int, default=None)
    runs = sub.add_parser("runs", help="list recent Ask runs, or show one with --show ID")
    runs.add_argument("--show", type=int, default=None)
    runs.add_argument("--limit", type=int, default=20)
    sub.add_parser("mcp", help="serve the read-only job tools over MCP (stdio) for VS Code, Claude Desktop, ...")
    ev = sub.add_parser("eval", help="run the Ask agent on evals/ask_cases.yaml and check its answers")
    ev.add_argument("--repeat", type=int, default=3, help="runs per case: the model varies")
    ev.add_argument("--only", help="comma-separated case ids")
    ev.add_argument("--pause", type=float, default=3.0, help="seconds between runs (free-tier limits)")

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
    elif args.cmd == "rescore":
        from . import db, pipeline
        print(f"Re-scored {pipeline.rescore(db.connect())} jobs")
    elif args.cmd == "ask":
        from . import agent
        steps = args.max_steps or agent.MAX_STEPS
        agent.print_result(agent.ask(args.question, max_steps=steps))
    elif args.cmd == "mcp":
        from . import mcp_server
        mcp_server.main()
    elif args.cmd == "eval":
        from . import evals
        cases = evals.load_cases(args.only.split(",") if args.only else None)
        print(f"{len(cases)} cases x {args.repeat} runs, OmniRoute cache bypassed")
        report = evals.evaluate(cases, repeat=args.repeat, pause=args.pause)
        path = evals.save(report)
        evals.print_report(report, evals.previous(path))
        print(f"\nsaved {path.relative_to(evals.ROOT)}")
    elif args.cmd == "runs":
        import json
        from . import agent, db
        conn = db.connect()
        if args.show is not None:
            run = agent.load_run(conn, args.show)
            if run is None:
                print(f"no run {args.show}")
            else:
                agent.print_result(run)
        else:
            for r in agent.recent_runs(conn, args.limit):
                calls = sum(s["kind"] == "model" for s in json.loads(r["steps"]))
                models = ",".join(m.split("/")[-1] for m in json.loads(r["models"]))
                print(f"{r['id']:5d}  {r['started_at'][:16]}  {r['source']:4s}  {r['stopped'][:9]:9s} "
                      f"{calls}c {r['tokens_in'] + r['tokens_out']:6d}t {r['seconds']:5.1f}s  "
                      f"{models[:24]:24s}  {r['question'][:60]}")
    elif args.cmd == "health":
        from . import db, pipeline
        conn = db.connect()
        for r in reversed(db.latest_company_runs(conn)):
            status = pipeline.health_status(bool(r["ok"]), r["raw_count"], r["india_count"], None)
            if r["ats"] == "custom":
                status = "manual"           # no scraper for this site: the same label the app uses
            if status != "ok":
                print(f"[{status:6}] {r['company']:28} {r['ats']:16} {r['error'] or '0 postings'}")


if __name__ == "__main__":
    main()
