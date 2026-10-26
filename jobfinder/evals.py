"""Evals for the Ask agent: real questions, run against the real model, checked by code.

    python -m jobfinder eval                  # every case in evals/ask_cases.yaml, 3 times each
    python -m jobfinder eval --only devops,remote --repeat 5

Each run bypasses OmniRoute's cache, so repeats measure how much the model varies. A run
stopped by the model service (rate limits) is "not scored": a provider outage is not a
wrong answer. Results go to evals/results/<time>.json and are compared with the last file.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

import yaml

from . import agent, agent_tools, db, queries

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = ROOT / "evals" / "ask_cases.yaml"
RESULTS_DIR = ROOT / "evals" / "results"
ENGLISH = {"the", "job", "jobs", "are", "is", "in", "no", "of", "and", "with", "for", "there",
           "match", "found", "your", "this", "that", "here", "not"}


def load_cases(only: list[str] | None = None) -> list[dict]:
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))
    return [c for c in cases if not only or c["id"] in only]


def _comparable(conn: sqlite3.Connection, filters: dict) -> dict:
    """Filters in one form, whoever wrote them: cities resolved, words lowercased and sorted."""
    full = agent_tools.checked_filters(conn, **filters)
    words = (full["description_words"] or "").lower().split()
    anyof = [w.lower() for w in full["description_any"]]
    if len(anyof) == 1 and not words:          # "any of one word" is the same search as "all of it"
        words, anyof = anyof[0].split(), []
    full["description_words"] = " ".join(sorted(words))
    full["description_any"] = sorted(anyof)
    full["title_words"] = (full["title_words"] or "").lower()
    for key in ("roles", "levels", "employment_types", "cities", "statuses"):
        full[key] = sorted(full[key])
    return full


def _internal_names(conn: sqlite3.Connection) -> set[str]:
    """Tool and parameter names the answer should never show (only ones with an underscore:
    "roles" or "levels" are ordinary English)."""
    names = {"give_answer"}
    for tool in agent_tools.schemas(conn):
        names.add(tool["function"]["name"])
        names.update(tool["function"]["parameters"].get("properties", {}))
    return {n for n in names if "_" in n}


def check_run(conn: sqlite3.Connection, case: dict, result: agent.Result) -> dict[str, bool]:
    """Each check of one run: True passed, False failed. Only the checks the case asks for."""
    searches = [json.loads(s["arguments"] or "{}") for s in result.steps
                if s["kind"] == "tool" and s["tool"] == "search_jobs" and not s["failed"]]
    searches = [{k: v for k, v in s.items() if k not in ("sort", "limit")} for s in searches]
    expected = case.get("filters") or {}
    checks: dict[str, bool] = {}
    truth_total = None
    if expected:
        want = _comparable(conn, expected)
        where, args = agent_tools.filter_sql(want)
        truth_total = queries.find_jobs(conn, where, args, want["title_words"] or None,
                                        "score", None, 1, 1)[0]
        try:
            last = _comparable(conn, searches[-1]) if searches else None
        except (TypeError, agent_tools.ToolError):
            last = None
        checks["filters"] = last is not None and all(last[k] == want[k] for k in expected)
    if case.get("not_filters"):
        off = agent_tools._OFF
        checks["not_filters"] = not any(s.get(k) not in (None, off[k], "", []) for s in searches
                                        for k in case["not_filters"])
    if case.get("picks_match") and expected:
        ids = result.job_ids
        if not ids:
            checks["picks_match"] = truth_total == 0
        else:
            matching = conn.execute(
                f"SELECT COUNT(*) FROM jobs j LEFT JOIN user_state u ON u.job_id = j.id "
                f"WHERE {where} AND j.id IN ({','.join('?' * len(ids))})", [*args, *ids]).fetchone()[0]
            checks["picks_match"] = matching == len(ids)
    if case.get("states_total"):
        numbers = {int(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*\b", result.answer)}
        checks["states_total"] = truth_total in numbers
    if case.get("no_jobs"):
        checks["no_jobs"] = not result.job_ids
    words = set(re.findall(r"[a-z]+", result.answer.lower()))
    checks["english"] = len(words & ENGLISH) >= 2
    checks["no_internal_names"] = not any(n in result.answer for n in _internal_names(conn))
    return checks


def evaluate(cases: list[dict], repeat: int = 3, pause: float = 3.0, impl: str = "ours") -> dict:
    """impl "langgraph" runs the same cases through agent_lg (Part 9's comparison)."""
    if impl == "langgraph":
        from . import agent_lg
        ask = agent_lg.ask
    else:
        ask = agent.ask
    conn = db.connect()
    runs = []
    for case in cases:
        for attempt in range(1, repeat + 1):
            result = ask(case["question"], conn=conn, source="eval", cache=False)
            models = [s["model"] for s in result.steps if s["kind"] == "model"]
            run = {"case": case["id"], "attempt": attempt, "stopped": result.stopped,
                   "model": models[-1] if models else None, "tokens": result.tokens_in + result.tokens_out,
                   "seconds": result.seconds, "answer": result.answer}
            if result.stopped == "error":
                run["scored"] = False                 # the provider failed, not the agent
            else:
                run["scored"] = True
                run["checks"] = check_run(conn, case, result)
                run["passed"] = all(run["checks"].values())
            runs.append(run)
            mark = "--" if not run["scored"] else "ok" if run["passed"] else "FAIL"
            failed = [k for k, v in run.get("checks", {}).items() if not v]
            print(f"  {mark:4s} {case['id']:20s} #{attempt}  {(run['model'] or '').split('/')[-1]:18s}"
                  f" {result.seconds:5.1f}s  {' '.join(failed)}", flush=True)
            time.sleep(pause)
    conn.close()
    report = summarize(runs)
    report["impl"] = impl
    return report


def _rate(passed: int, total: int) -> str:
    return f"{passed}/{total} ({100 * passed / total:.0f}%)" if total else "-"


def summarize(runs: list[dict]) -> dict:
    scored = [r for r in runs if r["scored"]]
    names = sorted({k for r in scored for k in r["checks"]})
    by_check = {n: [sum(r["checks"][n] for r in scored if n in r["checks"]),
                    sum(1 for r in scored if n in r["checks"])] for n in names}
    by_case: dict[str, list[int]] = {}
    by_model: dict[str, list[int]] = {}
    for r in scored:
        for table, key in ((by_case, r["case"]), (by_model, r["model"] or "?")):
            table.setdefault(key, [0, 0])
            table[key][0] += r["passed"]
            table[key][1] += 1
    return {
        "time": db.now(), "runs": runs, "scored": len(scored), "not_scored": len(runs) - len(scored),
        "passed": sum(r["passed"] for r in scored), "by_check": by_check, "by_case": by_case,
        "by_model": by_model,
        "avg_tokens": round(sum(r["tokens"] for r in scored) / len(scored)) if scored else 0,
        "avg_seconds": round(sum(r["seconds"] for r in scored) / len(scored), 1) if scored else 0,
    }


def save(report: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "" if report.get("impl", "ours") == "ours" else f"-{report['impl']}"
    path = RESULTS_DIR / f"{report['time'].replace(':', '')}{suffix}.json"
    path.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return path


def previous(before: Path) -> dict | None:
    # The latest earlier run of the same implementation: ours and LangGraph's are not compared here.
    langgraph = before.stem.endswith("-langgraph")
    older = sorted(p for p in RESULTS_DIR.glob("*.json")
                   if p.name < before.name and p.stem.endswith("-langgraph") == langgraph)
    return json.loads(older[-1].read_text(encoding="utf-8")) if older else None


def print_report(report: dict, last: dict | None) -> None:
    print(f"\nAll checks passed in {_rate(report['passed'], report['scored'])} scored runs; "
          f"{report['not_scored']} not scored (model service failed). "
          f"Average {report['avg_tokens']} tokens, {report['avg_seconds']} s per question.")
    print("\nby check:")
    for name, (p, t) in report["by_check"].items():
        change = ""
        if last and name in last["by_check"] and last["by_check"][name][1]:
            lp, lt = last["by_check"][name]
            delta = 100 * p / t - 100 * lp / lt
            change = f"   {'+' if delta >= 0 else ''}{delta:.0f} pts vs last" + ("   <-- worse" if delta < -5 else "")
        print(f"  {name:18s} {_rate(p, t):>14s}{change}")
    print("\nby model that wrote the answer:")
    for model, (p, t) in sorted(report["by_model"].items()):
        print(f"  {model:32s} {_rate(p, t)}")
    weak = [(c, p, t) for c, (p, t) in report["by_case"].items() if p < t]
    if weak:
        print("\ncases that did not pass every time:")
        for c, p, t in sorted(weak, key=lambda x: x[1] / x[2]):
            print(f"  {c:20s} {_rate(p, t)}")
