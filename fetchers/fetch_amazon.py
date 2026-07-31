import logging
import asyncio
import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
PAGE_SIZE = 100
MAX_PAGES = 30  # Max 3000 jobs

def _build_url(offset: int) -> str:
    # base_query=software ensures we get SWE roles without pulling all 3000+ Amazon India jobs.
    # We set result_limit=100 to reduce the number of requests.
    return f"https://www.amazon.jobs/en/search.json?base_query=software&country=IND&result_limit={PAGE_SIZE}&offset={offset}"

async def _fetch_page(client: httpx.AsyncClient, offset: int) -> tuple[list[dict], int]:
    """Fetch a single page of Amazon jobs."""
    url = _build_url(offset)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate"  # prevents httpx zstd decompression errors
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = await client.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            jobs = data.get("jobs", [])
            total = int(data.get("hits", 0))
            return jobs, total
        except Exception as e:
            logger.warning("[Amazon] offset %d attempt %d failed: %s", offset, attempt + 1, e)
            await asyncio.sleep(2 ** attempt)

    logger.error("[Amazon] all %d retries exhausted at offset %d", MAX_RETRIES, offset)
    return [], 0


def _normalise(job: dict) -> dict:
    """Convert an Amazon job dictionary into the standard schema."""
    title = job.get("title", "")
    location = job.get("normalized_location", job.get("location", ""))
    url = job.get("url_next_step", "")
    
    desc = job.get("description", "")
    basic = job.get("basic_qualifications", "")
    pref = job.get("preferred_qualifications", "")
    full_desc = f"{desc}\\n{basic}\\n{pref}"

    emp_type = job.get("job_schedule_type", "").title()
    if "full-time" in emp_type.lower() or "full time" in emp_type.lower():
        emp_type = "Full-time"

    # Some roles might be explicitly marked as internships in description or type
    if "intern" in emp_type.lower() or job.get("is_intern"):
        emp_type = "Intern"

    return {
        "company": "Amazon",
        "title": title,
        "location": location,
        "employment_type": emp_type,
        "ats_source": "Amazon",
        "apply_url": url,
        "description": full_desc,
        "departments": job.get("job_category", ""),
        "date_fetched": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }


async def fetch_amazon(client: httpx.AsyncClient, delay: float = 2.0) -> list[dict]:
    """Fetch all software jobs from Amazon India."""
    all_jobs = []
    total = None
    offset = 0

    for page in range(MAX_PAGES):
        postings, total_count = await _fetch_page(client, offset)
        
        if total is None:
            total = total_count
            logger.info("[Amazon] total software jobs reported: %d", total)

        if not postings:
            break

        all_jobs.extend([_normalise(j) for j in postings])
        offset += PAGE_SIZE

        if offset >= total_count:
            break

        await asyncio.sleep(delay)

    logger.info("[Amazon] fetched %d jobs (of %d total)", len(all_jobs), total or 0)
    return all_jobs
