"""Claude as the judge for jobs that do not state their pay.

For each job Claude estimates the likely annual pay band in India (or monthly
stipend, expressed as LPA, for internships) from the company, title, level,
location and description, and flags listings that look unpaid or like scams.
Results are stored per job, so each job is sent once.

Needs ANTHROPIC_API_KEY. Run:  python -m jobfinder brain --limit 300
"""

from __future__ import annotations

import json
import logging
import os

import anthropic

from . import db, pay, score

logger = logging.getLogger("jobfinder.brain")

MODEL = "claude-opus-5-5"
BATCH = 20

SYSTEM = """You assess job postings for a candidate in India who wants to avoid \
low-paid, unpaid and fake listings.

For every job you are given, estimate the realistic pay the company would offer for \
that exact role and level in India. Base it on what salary sites such as AmbitionBox, \
Glassdoor and Levels.fyi report as the average for that role and experience level at \
that specific company, adjusted for the location and for anything in the description. \
When you do not know the company, estimate from what comparable companies of its size \
and sector pay, and say in the reason that it is a guess from peers.

- For full-time roles give annual CTC in lakhs per annum (LPA).
- For internships give the monthly stipend multiplied by 12, in LPA (a 50,000 per \
month stipend is 6 LPA).
- Give a range you would bet on, not a best case. If you genuinely cannot tell, \
set both numbers to null rather than guessing.
- flag is "ok" normally; "unpaid" if the posting is unpaid or stipend-free in \
substance (including "performance based" pay with no fixed amount); "suspicious" if \
it shows scam markers: the candidate must pay a fee or deposit, it is a paid course \
or training sold as a job, the employer is unidentifiable, the pay is implausible \
for the work, or the text is a generic template with no real role.
- reason is one short sentence the candidate can read.

Return one result per job, using the job's id exactly as given."""

SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "est_min_lpa": {"type": ["number", "null"]},
                    "est_max_lpa": {"type": ["number", "null"]},
                    "flag": {"type": "string", "enum": ["ok", "unpaid", "suspicious"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "est_min_lpa", "est_max_lpa", "flag", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def _describe(job: dict) -> dict:
    return {
        "id": job["id"],
        "company": job["company"],
        "title": job["title"],
        "location": job["location"],
        "level": job["level"],
        "type": job["employment_type"],
        "experience_years": job["exp_min"],
        "listed_on": job["source"],
        "description": (job["description"] or "")[:1800],
    }


def _ask(client: anthropic.Anthropic, jobs: list[dict]) -> list[dict]:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        # A declined request is re-run on Anthropic's recommended fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        thinking={"type": "adaptive"},
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": "Assess these jobs:\n\n"
            + json.dumps([_describe(j) for j in jobs], ensure_ascii=False, indent=1),
        }],
    )
    if response.stop_reason == "refusal":
        logger.warning("Claude declined a batch; skipping it")
        return []
    if response.stop_reason == "max_tokens":
        logger.warning("Claude's answer was cut off; skipping this batch")
        return []
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["results"]


def run(limit: int = 300) -> dict:
    """Assess up to `limit` active jobs with no stated pay, best matches first."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise SystemExit(
            "No Claude API key found. Create one at https://console.anthropic.com, then run:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n  python -m jobfinder brain"
        )
    client = anthropic.Anthropic()
    profile = score.load_profile()
    conn = db.connect()
    rows = [db.job_to_dict(r) for r in conn.execute(
        "SELECT * FROM jobs WHERE is_active=1 AND brain_done=0 AND salary_max_lpa IS NULL "
        "AND COALESCE(est_source, 'band') IN ('band', 'market') ORDER BY score DESC LIMIT ?",
        (limit,),
    )]
    done = flagged = 0
    for start in range(0, len(rows), BATCH):
        batch = rows[start:start + BATCH]
        by_id = {j["id"]: j for j in batch}
        try:
            results = _ask(client, batch)
        except anthropic.AuthenticationError:
            raise SystemExit("ANTHROPIC_API_KEY is missing or invalid.")
        except anthropic.RateLimitError:
            logger.warning("Rate limited; stopping early. Run the command again later.")
            break
        except anthropic.APIStatusError as exc:
            logger.warning("Claude API error %s on a batch; skipping it", exc.status_code)
            continue
        except anthropic.APIConnectionError:
            logger.warning("Could not reach the Claude API; stopping.")
            break
        for result in results:
            job = by_id.get(result["id"])
            if not job:
                continue
            job.update(est_min_lpa=result["est_min_lpa"], est_max_lpa=result["est_max_lpa"],
                       brain_flag=result["flag"], brain_note=result["reason"],
                       est_source="claude" if result["est_max_lpa"] is not None else None)
            verdict = pay.judge(job, profile)
            job["pay_verdict"] = verdict
            value, reasons = score.score_job(job, profile)
            conn.execute(
                "UPDATE jobs SET est_min_lpa=?, est_max_lpa=?, est_source=?, brain_flag=?, "
                "brain_note=?, brain_done=1, pay_verdict=?, score=?, score_reasons=? WHERE id=?",
                (result["est_min_lpa"], result["est_max_lpa"], job["est_source"], result["flag"],
                 result["reason"],
                 verdict, value, json.dumps(reasons), job["id"]),
            )
            done += 1
            flagged += verdict in pay.BAD
        conn.commit()
        print(f"  assessed {done}/{len(rows)}")
    conn.close()
    return {"assessed": done, "flagged_low_unpaid_or_suspicious": flagged, "pending": len(rows) - done}
