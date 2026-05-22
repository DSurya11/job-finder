"""Job Finder — Apify-powered scraper for India internships.

Flow:
  1. Load user_profile.yaml + resume PDF.
  2. Call configured Apify actors in parallel
     (LinkedIn Jobs, LinkedIn Posts, Indeed India, Naukri, Internshala, Wellfound, Glassdoor).
  3. Filter results: India-only, no excluded keywords, deduplicate by URL.
  4. Export jobs.xlsx — formatted for upload to Claude AI.
  5. Save <name>_claude_prompt.txt — paste directly into Claude.ai.

Usage:
  python job_finder.py
  python job_finder.py --resume "path/to/resume.pdf"
  python job_finder.py --profile user_profile.yaml --output jobs.xlsx
"""

import argparse
import asyncio
import os
import time
from pathlib import Path
from urllib.parse import quote_plus

import httpx
import openpyxl
import yaml
from dotenv import load_dotenv
from openpyxl.styles import Alignment, Font, PatternFill
from PyPDF2 import PdfReader

load_dotenv()

APIFY_BASE = "https://api.apify.com/v2"
APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
OUTPUT_EXCEL = os.getenv("OUTPUT_EXCEL", "jobs.xlsx")
POLL_INTERVAL = 8    # seconds between run-status checks
RUN_TIMEOUT = 420    # max seconds to wait for one actor run
MAX_PARALLEL = 4     # concurrent Apify runs

# ---------------------------------------------------------------------------
# Location filter keywords
# ---------------------------------------------------------------------------
INDIA_LOCS = {
    "india", "delhi", "new delhi", "mumbai", "bangalore", "bengaluru",
    "hyderabad", "chennai", "pune", "kolkata", "noida", "gurugram",
    "gurgaon", "ahmedabad", "jaipur", "bhopal", "indore", "kochi",
    "remote", "work from home", "wfh", "pan india", "anywhere in india",
}
NON_INDIA_LOCS = {
    "usa", "united states", "u.s.", " us ", "uk", "united kingdom",
    "canada", "australia", "germany", "france", "singapore", "dubai",
    "uae", "netherlands", "sweden", "japan", "china", "korea", "brazil",
    "new york", "san francisco", "london", "toronto", "sydney",
}


# ---------------------------------------------------------------------------
# Profile & resume helpers
# ---------------------------------------------------------------------------
def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def read_resume(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"  Warning: resume not found at {path}")
        return ""
    reader = PdfReader(str(p))
    return "".join(page.extract_text() or "" for page in reader.pages)


# ---------------------------------------------------------------------------
# Apify API helpers
# ---------------------------------------------------------------------------
async def _start_run(
    client: httpx.AsyncClient, actor_id: str, payload: dict
) -> str | None:
    try:
        r = await client.post(
            f"{APIFY_BASE}/acts/{actor_id}/runs",
            params={"token": APIFY_TOKEN},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        run_id = r.json()["data"]["id"]
        print(f"  [{actor_id}] started → {run_id}")
        return run_id
    except Exception as exc:
        print(f"  [{actor_id}] start failed: {exc}")
        return None


async def _wait_run(
    client: httpx.AsyncClient, run_id: str, label: str
) -> bool:
    deadline = time.monotonic() + RUN_TIMEOUT
    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL)
        try:
            r = await client.get(
                f"{APIFY_BASE}/actor-runs/{run_id}",
                params={"token": APIFY_TOKEN},
                timeout=15,
            )
            status = r.json()["data"]["status"]
            if status == "SUCCEEDED":
                return True
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                print(f"  [{label}] run ended with status: {status}")
                return False
        except Exception as exc:
            print(f"  [{label}] poll error: {exc}")
    print(f"  [{label}] timed out after {RUN_TIMEOUT}s")
    return False


async def _fetch_items(client: httpx.AsyncClient, run_id: str) -> list:
    try:
        r = await client.get(
            f"{APIFY_BASE}/actor-runs/{run_id}/dataset/items",
            params={"token": APIFY_TOKEN, "format": "json", "limit": 300},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json() or []
    except Exception as exc:
        print(f"  fetch error: {exc}")
    return []


async def run_actor(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    actor_id: str,
    payload: dict,
    label: str,
) -> list:
    async with sem:
        run_id = await _start_run(client, actor_id, payload)
        if not run_id:
            return []
        ok = await _wait_run(client, run_id, label)
        if not ok:
            return []
        items = await _fetch_items(client, run_id)
        print(f"  [{label}] → {len(items)} items")
        return items


# ---------------------------------------------------------------------------
# Per-source result normalizers
# ---------------------------------------------------------------------------
def _s(d: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        if d.get(k):
            return str(d[k]).strip()
    return default


def _title_from_post_text(text: str) -> str:
    for line in text.split("\n"):
        line = line.strip()
        if 10 <= len(line) <= 80 and any(
            w in line.lower()
            for w in ("intern", "engineer", "developer", "hiring", "scientist", "analyst")
        ):
            return line[:80]
    return text[:60]


NORMALIZERS: dict = {
    "linkedin_jobs": lambda x: {
        "title": _s(x, "title", "jobTitle"),
        "company": _s(x, "company", "companyName"),
        "location": _s(x, "location", "jobLocation"),
        "salary": _s(x, "salary", "salaryInfo"),
        "url": _s(x, "url", "jobUrl", "link"),
        "description": _s(x, "description", "jobDescription")[:700],
        "source": "LinkedIn Jobs",
        "posted": _s(x, "postedAt", "publishedAt", "date"),
    },
    "linkedin_posts": lambda x: {
        "title": _s(x, "title") or _title_from_post_text(_s(x, "text", "content", "postText")),
        "company": _s(x, "authorName", "authorCompany", "company"),
        "location": _s(x, "location"),
        "salary": "",
        "url": _s(x, "postUrl", "url", "link"),
        "description": _s(x, "text", "content", "postText")[:700],
        "source": "LinkedIn Post",
        "posted": _s(x, "postedAt", "timestamp", "date"),
    },
    "indeed": lambda x: {
        "title": _s(x, "positionName", "title", "jobTitle"),
        "company": _s(x, "company", "companyName"),
        "location": _s(x, "location", "jobLocation"),
        "salary": _s(x, "salary", "salaryText"),
        "url": _s(x, "url", "jobUrl", "externalApplyLink"),
        "description": _s(x, "description", "snippet")[:700],
        "source": "Indeed",
        "posted": _s(x, "date", "postedAt"),
    },
    "glassdoor": lambda x: {
        "title": _s(x, "jobTitle", "title"),
        "company": _s(x, "employerName", "company"),
        "location": _s(x, "location", "jobLocation"),
        "salary": _s(x, "payPeriod", "salary", "salaryEstimate"),
        "url": _s(x, "jobViewUrl", "url", "link"),
        "description": _s(x, "jobDescription", "description")[:700],
        "source": "Glassdoor",
        "posted": _s(x, "listingDate", "postedAt", "date"),
    },
    "naukri": lambda x: {
        "title": _s(x, "jobTitle", "title"),
        "company": _s(x, "companyName", "company"),
        "location": _s(x, "location", "jobLocation"),
        "salary": _s(x, "salary", "salaryDetail"),
        "url": _s(x, "jdURL", "url", "link"),
        "description": _s(x, "jobDescription", "description")[:700],
        "source": "Naukri",
        "posted": _s(x, "freshness", "postedAt", "date"),
    },
    "internshala": lambda x: {
        "title": _s(x, "title", "internshipTitle", "profile"),
        "company": _s(x, "company", "companyName", "organizationName"),
        "location": _s(x, "location", "city", "jobLocation") or "India",
        "salary": _s(x, "stipend", "salary", "stipendAmount", "monthlyStipend"),
        "url": _s(x, "url", "link", "applyLink", "internshipUrl"),
        "description": _s(x, "description", "about", "jobDescription", "details")[:700],
        "source": "Internshala",
        "posted": _s(x, "postedOn", "postedAt", "startDate", "date"),
    },
    "wellfound": lambda x: {
        "title": _s(x, "title", "jobTitle", "role"),
        "company": _s(x, "company", "companyName", "startupName", "organizationName"),
        "location": _s(x, "location", "jobLocation", "remote"),
        "salary": _s(x, "compensation", "salary", "equity", "salaryRange"),
        "url": _s(x, "url", "jobUrl", "link", "applyUrl"),
        "description": _s(x, "description", "jobDescription", "about")[:700],
        "source": "Wellfound",
        "posted": _s(x, "postedAt", "createdAt", "date"),
    },
}


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def is_india_job(job: dict) -> bool:
    # Internshala and Naukri are India-only platforms — always pass
    if job.get("source") in ("Internshala", "Naukri"):
        return True
    loc = (job.get("location") or "").lower()
    desc = (job.get("description") or "").lower()
    if any(kw in loc for kw in NON_INDIA_LOCS):
        return False
    if any(kw in loc for kw in INDIA_LOCS):
        return True
    if not loc:
        return any(kw in desc for kw in INDIA_LOCS)
    return False


def passes_role_filter(job: dict, profile: dict) -> bool:
    exclude = [
        w.lower()
        for w in profile.get("job_preferences", {}).get("exclude_keywords", [])
    ]
    combined = (job.get("title", "") + " " + job.get("description", "")).lower()
    return not any(w in combined for w in exclude)


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
_H_FILL = PatternFill("solid", fgColor="1F4E79")
_ALT_FILL = PatternFill("solid", fgColor="EBF3FB")
_H_FONT = Font(bold=True, color="FFFFFF", size=11)
_HEADERS = [
    "#", "Title", "Company", "Location",
    "Salary / Stipend", "Source", "Posted", "Description", "URL",
]
_WIDTHS = [4, 38, 25, 22, 20, 16, 14, 65, 55]


def export_to_excel(jobs: list, path: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jobs"

    for col, (h, w) in enumerate(zip(_HEADERS, _WIDTHS), 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = _H_FONT
        cell.fill = _H_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[cell.column_letter].width = w
    ws.row_dimensions[1].height = 22

    for i, job in enumerate(jobs, 1):
        row_vals = [
            i,
            job.get("title", ""),
            job.get("company", ""),
            job.get("location", ""),
            job.get("salary", ""),
            job.get("source", ""),
            job.get("posted", ""),
            job.get("description", ""),
            job.get("url", ""),
        ]
        for col, val in enumerate(row_vals, 1):
            cell = ws.cell(row=i + 1, column=col, value=val or "")
            cell.alignment = Alignment(wrap_text=(col == 8), vertical="top")
            if i % 2 == 0:
                cell.fill = _ALT_FILL

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)
    print(f"Saved {len(jobs)} jobs → {path}")


# ---------------------------------------------------------------------------
# Claude AI prompt builder
# ---------------------------------------------------------------------------
def build_claude_prompt(profile: dict, resume_text: str, job_count: int) -> str:
    p = profile.get("personal", {})
    edu = profile.get("education", {})
    prefs = profile.get("job_preferences", {})
    skills = profile.get("skills", {})
    projects = profile.get("projects", [])
    all_skills = (
        skills.get("primary", [])
        + skills.get("secondary", [])
        + skills.get("ml_ai", [])
    )
    project_lines = "\n".join(
        f"  - {proj['name']}: {proj.get('tech', '')} — {proj.get('description', '')}"
        for proj in projects
    )
    resume_snippet = (
        resume_text[:2500] if resume_text else "(resume not loaded — please attach the PDF)"
    )

    return f"""I have attached an Excel file containing {job_count} job listings scraped from \
LinkedIn Jobs, LinkedIn Posts, Indeed India, and Glassdoor — all pre-filtered for India. \
Help me find the best internship matches.

## My Profile
Name: {p.get("name", "")}
Education: {edu.get("degree", "")} at {edu.get("institution", "")} | {edu.get("year", "")} | GPA: {edu.get("gpa", "")}
Current location: {p.get("location", "")}
Target locations: {", ".join(prefs.get("preferred_locations", ["India"]))}
Job type: {prefs.get("type", "internship")} — Paid only: {prefs.get("paid_only", True)}
Target roles: {", ".join(prefs.get("roles", []))}
Skills: {", ".join(all_skills)}

## Projects
{project_lines}

## Resume Text
{resume_snippet}

## Your Task
1. **Filter out**:
   - Non-India locations
   - Unpaid / stipend-unknown roles (unless company is top-tier and experience value is very high)
   - Non-tech roles, product pages, spam
   - Roles explicitly requiring 3+ years of experience
   - Duplicate URLs

2. **Score** each surviving job 0–10 on how well it matches my actual skill stack \
(use the Description column — do not rely on the Excel score column).

3. **Group into tiers**:
   - **Tier 1 – Apply Today**: Python / FastAPI backend intern, India, paid, stipend stated
   - **Tier 2 – Strong Match**: AI/ML, full-stack (React + Python), or Node.js intern, India, paid
   - **Tier 3 – Bulk Apply**: Decent fit, quick turnaround, still legitimate

4. **Per job card show**: Title · Company · Location · Stipend · Score/10 · Why it fits · Direct URL

5. End with a summary line: `X rows → Y after filters → Z picks shown`

**Preferences**: Remote or Hyderabad strongly preferred. \
Only 100% legitimate postings — no fake internship farms. \
For LinkedIn Posts, include only if a direct application URL is visible in the Description column.
"""


# ---------------------------------------------------------------------------
# Actor orchestration
# ---------------------------------------------------------------------------
async def collect_jobs(
    client: httpx.AsyncClient,
    profile: dict,
    sem: asyncio.Semaphore,
) -> list:
    actor_cfg = profile.get("apify_actors", {})
    keywords = profile.get("search", {}).get(
        "keywords", ["python backend intern India"]
    )

    tasks: list[tuple[str, str, dict]] = []

    def queue(source_key: str, extra_payload: dict) -> None:
        cfg = actor_cfg.get(source_key, {})
        if not cfg.get("enabled", True):
            return
        actor_id = cfg.get("actor_id", "").strip()
        if not actor_id:
            print(f"  Skipping {source_key}: no actor_id configured in user_profile.yaml")
            return
        merged = {**cfg.get("input_template", {}), **extra_payload}
        tasks.append((source_key, actor_id, merged))

    # LinkedIn Jobs — actor takes search page URLs, not a bare keyword
    for kw in keywords[:3]:
        li_url = (
            "https://www.linkedin.com/jobs/search/"
            f"?keywords={quote_plus(kw)}&location=India&position=1&pageNum=0"
        )
        queue("linkedin_jobs", {"startUrls": [{"url": li_url}]})

    # LinkedIn Posts — hiring posts mentioning the role
    for kw in keywords[:2]:
        queue("linkedin_posts", {"searchTerms": [f"hiring {kw} India"], "maxResults": 30})

    # Indeed India
    for kw in keywords[:3]:
        queue("indeed", {"position": kw})

    # Naukri — biggest India job board
    for kw in keywords[:3]:
        queue("naukri", {"position": kw})

    # Internshala — best source for India internships
    for kw in keywords[:3]:
        queue("internshala", {"keyword": kw})

    # Wellfound (AngelList) — startups
    for kw in keywords[:2]:
        queue("wellfound", {"searchQuery": kw, "location": "India"})

    # Glassdoor
    for kw in keywords[:2]:
        queue("glassdoor", {"keyword": kw})

    print(f"\nQueued {len(tasks)} actor runs...\n")

    coros = [
        run_actor(client, sem, actor_id, payload, f"{src}:{idx}")
        for idx, (src, actor_id, payload) in enumerate(tasks)
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)

    all_jobs: list[dict] = []
    for (source_key, _, _), result in zip(tasks, results):
        if isinstance(result, Exception):
            print(f"  Error in {source_key}: {result}")
            continue
        norm = NORMALIZERS.get(source_key, lambda x: x)
        for item in result:
            try:
                all_jobs.append(norm(item))
            except Exception:
                pass

    return all_jobs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Job Finder — Apify-powered India internship scraper"
    )
    ap.add_argument("--profile", default="user_profile.yaml", help="Path to user_profile.yaml")
    ap.add_argument("--resume", default=os.getenv("RESUME_PATH", ""), help="Path to resume PDF")
    ap.add_argument("--output", default=OUTPUT_EXCEL, help="Output Excel filename")
    return ap.parse_args()


async def main() -> None:
    args = parse_args()

    if not APIFY_TOKEN:
        print("ERROR: APIFY_TOKEN is not set.")
        print("  1. Get your token: https://console.apify.com/settings/integrations")
        print("  2. Create a .env file here and add:  APIFY_TOKEN=your_token_here")
        return

    if not Path(args.profile).exists():
        print(f"ERROR: Profile file not found: {args.profile}")
        print("  Fill in user_profile.yaml before running.")
        return

    profile = load_profile(args.profile)
    print(f"Profile  : {profile.get('personal', {}).get('name', 'Unknown')}")

    resume_path = args.resume or profile.get("resume_path", "")
    resume_text = read_resume(resume_path) if resume_path else ""
    if resume_text:
        print(f"Resume   : {len(resume_text)} chars from {resume_path}")
    else:
        print("Resume   : not loaded (set resume_path in user_profile.yaml or use --resume)")

    sem = asyncio.Semaphore(MAX_PARALLEL)
    async with httpx.AsyncClient() as client:
        all_jobs = await collect_jobs(client, profile, sem)

    print(f"\nCollected       : {len(all_jobs)}")

    india_jobs = [j for j in all_jobs if is_india_job(j)]
    print(f"India-only      : {len(india_jobs)}")

    filtered = [j for j in india_jobs if passes_role_filter(j, profile)]
    print(f"After role filter: {len(filtered)}")

    seen: set[str] = set()
    unique: list[dict] = []
    for j in filtered:
        url = j.get("url", "")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        unique.append(j)
    print(f"After dedup     : {len(unique)}")

    if not unique:
        print("\nNo jobs found. Check your actor IDs in user_profile.yaml and APIFY_TOKEN.")
        return

    output_path = args.output
    export_to_excel(unique, output_path)

    prompt = build_claude_prompt(profile, resume_text, len(unique))
    prompt_file = Path(output_path).stem + "_claude_prompt.txt"
    Path(prompt_file).write_text(prompt, encoding="utf-8")
    print(f"Claude prompt   → {prompt_file}")

    print("\n" + "=" * 60)
    print("NEXT STEPS — Score your jobs with Claude AI:")
    print("  1. Open https://claude.ai")
    print(f"  2. Attach:  {output_path}")
    if resume_path and Path(resume_path).exists():
        print(f"  3. Attach:  {resume_path}  (your resume PDF)")
    print(f"  4. Paste the contents of:  {prompt_file}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
