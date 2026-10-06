"""Sources that are not a standard ATS board.

Two kinds live here:
  - big-company career sites with their own listing format (Google, Apple,
    Microsoft), and
  - aggregators (LinkedIn's logged-out job search, Internshala) whose postings
    belong to many companies, so each raw posting carries its own `company`.

LinkedIn is read only through the public, logged-out search pages: no account
or cookies are used. Its user agreement still forbids automated collection, so
this source is throttled hard and can be switched off with `enabled: false`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from .sources import UA

logger = logging.getLogger(__name__)

HTML_HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-IN,en;q=0.9"}


async def _get(client: httpx.AsyncClient, url: str, *, params=None, tries: int = 4,
               pause: float = 4.0) -> httpx.Response:
    """GET with backoff on throttling."""
    for attempt in range(tries):
        resp = await client.get(url, params=params, headers=HTML_HEADERS, timeout=40)
        if resp.status_code in (429, 999, 502, 503) and attempt < tries - 1:
            await asyncio.sleep(pause * (attempt + 1))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError("unreachable")


# ── LinkedIn (logged-out job search) ─────────────────────────────────────────

_LI_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_LI_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
DEFAULT_KEYWORDS = [
    "software engineer", "software developer", "backend developer", "full stack developer",
    "software engineer intern", "machine learning engineer", "data engineer",
    "frontend developer", "devops engineer", "data scientist",
]


def _parse_linkedin_cards(html: str) -> list[dict]:
    out = []
    for card in BeautifulSoup(html, "html.parser").select("[data-entity-urn*='jobPosting']"):
        job_id = card["data-entity-urn"].rsplit(":", 1)[-1]
        title = card.select_one(".base-search-card__title")
        company = card.select_one(".base-search-card__subtitle")
        location = card.select_one(".job-search-card__location")
        posted = card.select_one("time")
        if not (title and company):
            continue
        out.append({
            "company": company.get_text(strip=True),
            "title": title.get_text(strip=True),
            "location": location.get_text(strip=True) if location else "India",
            "apply_url": f"https://www.linkedin.com/jobs/view/{job_id}",
            "posted_at": (posted.get("datetime") or "")[:10] if posted else "",
            "detail_kind": "linkedin",
            "detail_url": _LI_DETAIL.format(id=job_id),
            # The search itself is restricted to India.
            "india_confirmed": True,
        })
    return out


async def linkedin(client: httpx.AsyncClient, co: dict) -> list[dict]:
    keywords = co.get("keywords") or DEFAULT_KEYWORDS
    max_pages = int(co.get("max_pages", 15))
    window = co.get("posted_within", "r604800")     # seconds: r86400 = 24h, r604800 = week
    delay = float(co.get("delay", 1.2))
    seen: dict[str, dict] = {}
    for keyword in keywords:
        for page in range(max_pages):
            try:
                resp = await _get(client, _LI_SEARCH, params={
                    "keywords": keyword, "location": "India", "f_TPR": window,
                    "start": page * 10,
                })
            except httpx.HTTPError as exc:
                # Throttled or cut off: keep what we have, move to the next keyword.
                logger.warning("[LinkedIn] '%s' page %d: %s", keyword, page, exc)
                break
            cards = _parse_linkedin_cards(resp.text)
            if not cards:
                break
            for card in cards:
                seen.setdefault(card["apply_url"], card)
            await asyncio.sleep(delay)
    return list(seen.values())


def parse_linkedin_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one(".show-more-less-html__markup")
    criteria = {}
    for item in soup.select(".description__job-criteria-item"):
        key = item.select_one(".description__job-criteria-subheader")
        value = item.select_one(".description__job-criteria-text")
        if key and value:
            criteria[key.get_text(strip=True).lower()] = value.get_text(strip=True)
    return {
        "description_html": str(body) if body else "",
        "employment_type": criteria.get("employment type", ""),
    }


# ── Internshala ──────────────────────────────────────────────────────────────

_IS_BASE = "https://internshala.com"
DEFAULT_INTERNSHALA = [
    "software-development", "web-development", "backend-development",
    "full-stack-development", "python-django", "machine-learning", "data-science",
    "artificial-intelligence-ai", "front-end-development", "mobile-app-development",
]


def _parse_internshala(html: str) -> list[dict]:
    out = []
    for card in BeautifulSoup(html, "html.parser").select(".individual_internship[data-href]"):
        title = card.select_one(".job-internship-name")
        company = card.select_one(".company-name")
        if not (title and company):
            continue
        locations = card.select_one(".locations")
        stipend = card.select_one(".stipend")
        about = card.select_one(".about_job .text")
        skills = [s.get_text(strip=True) for s in card.select(".job_skill")]
        location = locations.get_text(" ", strip=True) if locations else ""
        stipend_text = stipend.get_text(" ", strip=True) if stipend else ""
        description = "\n".join(x for x in (
            about.get_text(" ", strip=True) if about else "",
            f"Skills: {', '.join(skills)}" if skills else "",
            f"Stipend: {stipend_text}" if stipend_text else "",
        ) if x)
        out.append({
            "company": company.get_text(strip=True),
            "title": title.get_text(strip=True),
            "location": location or "India",
            "employment_type": card.get("employment_type") or "internship",
            "description": description,
            "apply_url": _IS_BASE + card["data-href"],
            "detail_kind": "internshala",
            "detail_url": _IS_BASE + card["data-href"],
            # Internshala is an India-only board; "Work from home" has no city.
            "india_confirmed": True,
        })
    return out


async def internshala(client: httpx.AsyncClient, co: dict) -> list[dict]:
    categories = co.get("categories") or DEFAULT_INTERNSHALA
    max_pages = int(co.get("max_pages", 4))
    seen: dict[str, dict] = {}
    for category in categories:
        for page in range(1, max_pages + 1):
            url = f"{_IS_BASE}/internships/{category}-internship/"
            if page > 1:
                url += f"page-{page}/"
            try:
                resp = await _get(client, url)
            except httpx.HTTPError as exc:
                logger.warning("[Internshala] %s page %d: %s", category, page, exc)
                break
            cards = _parse_internshala(resp.text)
            if not cards:
                break
            for card in cards:
                seen.setdefault(card["apply_url"], card)
            await asyncio.sleep(0.8)
    return list(seen.values())


def parse_internshala_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    parts = [str(node) for node in soup.select(
        ".internship_details .text-container, .internship_details .round_tabs_container"
    )]
    return {"description_html": "\n".join(parts)}


# ── Google ───────────────────────────────────────────────────────────────────

_GOOGLE_URL = "https://www.google.com/about/careers/applications/jobs/results/"
_GOOGLE_DATA = re.compile(
    r"AF_initDataCallback\(\{key: 'ds:1', hash: '[^']+', data:(.*?), sideChannel: \{\}\}\);", re.S
)


def _html_at(row: list, index: int) -> str:
    cell = row[index] if len(row) > index else None
    return cell[1] if isinstance(cell, list) and len(cell) > 1 and cell[1] else ""


async def google(client: httpx.AsyncClient, co: dict) -> list[dict]:
    out, page, total = [], 1, None
    while True:
        resp = await _get(client, _GOOGLE_URL, params={"location": "India", "page": page})
        match = _GOOGLE_DATA.search(resp.text)
        if not match:
            raise ValueError("Google careers page layout changed: job data block not found")
        data = json.loads(match.group(1))
        rows = data[0] or []
        total = total if total is not None else (data[2] or 0)
        for row in rows:
            locations = "; ".join(loc[0] for loc in (row[9] or []) if loc and loc[0])
            slug = re.sub(r"[^a-z0-9]+", "-", row[1].lower()).strip("-")
            posted = row[12][0] if len(row) > 12 and row[12] else None
            out.append({
                "title": row[1],
                "location": locations,
                "description_html": "\n".join((
                    _html_at(row, 10), "<h3>Responsibilities</h3>", _html_at(row, 3),
                    _html_at(row, 4),
                )),
                "apply_url": f"{_GOOGLE_URL}{row[0]}-{slug}",
                "posted_at": datetime.fromtimestamp(posted, timezone.utc).strftime("%Y-%m-%d")
                if posted else "",
            })
        if not rows or len(out) >= total or page >= 60:
            return out
        page += 1
        await asyncio.sleep(0.5)


# ── Apple ────────────────────────────────────────────────────────────────────

_APPLE_DATA = re.compile(r'window\.__staticRouterHydrationData = JSON\.parse\("(.*?)"\);', re.S)


async def apple(client: httpx.AsyncClient, co: dict) -> list[dict]:
    out, page, total = [], 1, None
    while True:
        resp = await _get(client, "https://jobs.apple.com/en-in/search",
                          params={"location": "india-INDC", "page": page})
        match = _APPLE_DATA.search(resp.text)
        if not match:
            raise ValueError("Apple jobs page layout changed: hydration data not found")
        search = json.loads(json.loads(f'"{match.group(1)}"'))["loaderData"]["search"]
        rows = search.get("searchResults") or []
        total = total if total is not None else (search.get("totalRecords") or 0)
        for row in rows:
            locations = "; ".join(
                ", ".join(x for x in (loc.get("city"), loc.get("stateProvince"),
                                      loc.get("countryName")) if x)
                for loc in row.get("locations") or []
            )
            position = row.get("positionId") or str(row.get("id", "")).split("-")[-1]
            slug = row.get("transformedPostingTitle") or "job"
            out.append({
                "title": row.get("postingTitle") or "",
                "location": locations or "India",
                "description": row.get("jobSummary") or "",
                "departments": (row.get("team") or {}).get("teamName") or "",
                "apply_url": f"https://jobs.apple.com/en-in/details/{position}/{slug}",
                "posted_at": (row.get("postDateInGMT") or "")[:10],
                "india_confirmed": True,
            })
        if not rows or len(out) >= total or page >= 40:
            return out
        page += 1
        await asyncio.sleep(0.5)


# ── Eightfold "pcsx" career sites (Microsoft) ────────────────────────────────

async def pcsx(client: httpx.AsyncClient, co: dict) -> list[dict]:
    host, domain = co["host"], co["domain"]
    out, start, total = [], 0, None
    while True:
        resp = await client.get(
            f"https://{host}/api/pcsx/search",
            params={"domain": domain, "query": "", "location": "India", "start": start},
            headers={"User-Agent": UA}, timeout=40,
        )
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        rows = data.get("positions") or []
        total = total if total is not None else (data.get("count") or 0)
        for row in rows:
            codes = row.get("standardizedLocations") or []
            out.append({
                "title": row.get("name") or "",
                "location": "; ".join(row.get("locations") or []),
                "departments": row.get("department") or "",
                "apply_url": f"https://{host}{row.get('positionUrl')}",
                "posted_at": datetime.fromtimestamp(row["postedTs"], timezone.utc).strftime("%Y-%m-%d")
                if row.get("postedTs") else "",
                "detail_kind": "pcsx",
                "detail_url": f"https://{host}/api/pcsx/position_details"
                              f"?position_id={row.get('id')}&domain={domain}",
                "india_confirmed": "IN" in codes or not codes,
            })
        start += len(rows)
        if not rows or start >= total or start >= 3000:
            return out
        await asyncio.sleep(0.3)


# ── TurboHire career pages (Flipkart, Ola) ───────────────────────────────────

_TH_API = "https://thapi.azurewebsites.net/api"


async def turbohire(client: httpx.AsyncClient, co: dict) -> list[dict]:
    org, site = co["org_id"], co["site"].rstrip("/")
    headers = {"User-Agent": UA, "Origin": site, "Referer": site + "/"}
    token = await client.get(f"{_TH_API}/token/noauth", params={"orgId": org},
                             headers=headers, timeout=30)
    token.raise_for_status()
    headers["Authorization"] = f"Bearer {token.json()['access_token']}"
    resp = await client.post(
        f"{_TH_API}/careerpagev2/filteredjobs", params={"orgId": org, "pageType": 0},
        json={"searchtext": "", "jobType": [], "department": [], "location": [], "experience": []},
        headers=headers, timeout=40,
    )
    resp.raise_for_status()
    out = []
    for row in resp.json().get("Result") or []:
        location = row.get("JobLocation") or row.get("Location") or ""
        if isinstance(location, str) and location.startswith("["):
            location = json.loads(location)
        if isinstance(location, list):
            location = "; ".join(
                (x.get("Address") or "") if isinstance(x, dict) else str(x) for x in location
            )
        out.append({
            "title": row.get("JobTitle") or "",
            "location": location or "India",
            "departments": row.get("Department") or "",
            "description_html": row.get("JobDescription") or "",
            "apply_url": f"{site}/job/career?jobId={row.get('JobIdObfuscated') or row.get('JobId')}",
            "posted_at": (row.get("PublishedDate") or "")[:10],
            "india_confirmed": True,
        })
    return out


# ── Uber (needs a real browser: paging happens client-side) ──────────────────

_UBER_CARDS = """() => [...document.querySelectorAll("a[href*='/en/jobs/']")]
  .filter(a => /\\/jobs\\/\\d+\\/?$/.test(a.pathname))
  .map(a => [a.pathname, a.innerText.trim(),
             (a.closest("[class*='bg-card']") || a.parentElement).innerText])"""
_UBER_NOISE = {"Job removed", "Job saved", "Save job", "New"}


async def uber(client: httpx.AsyncClient, co: dict) -> list[dict]:
    from playwright.async_api import async_playwright

    out: dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(user_agent=UA, viewport={"width": 1366, "height": 900})
            await page.goto("https://jobs.uber.com/en/jobs/", wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_selector("a[href*='/en/jobs/']", timeout=30000)
            await page.wait_for_timeout(3000)   # let the page hydrate before clicking
            # The cookie dialog appears a few seconds in and covers the pager.
            consent = page.get_by_role("button", name="Essential Only")
            try:
                await consent.first.click(timeout=10000)
                await page.wait_for_timeout(500)
            except Exception:
                pass                      # no dialog this time
            for _ in range(200):
                cards = await page.evaluate(_UBER_CARDS)
                first = cards[0][0] if cards else ""
                for path, title, text in cards:
                    lines = [l.strip() for l in text.split("\n")
                             if l.strip() and l.strip() != title and l.strip() not in _UBER_NOISE]
                    url = f"https://jobs.uber.com{path}"
                    # Cards show "City, Region (+ N locations)" and then the team.
                    out.setdefault(url, {
                        "title": title,
                        "location": re.sub(r"\s*\+\s*\d+ locations?", "", lines[0]) if lines else "",
                        "departments": lines[1] if len(lines) > 1 else "",
                        "apply_url": url,
                        "detail_kind": "jsonld",
                        "detail_url": url,
                    })
                nxt = page.get_by_label("Go to next page").first
                if not await nxt.count() or await nxt.get_attribute("aria-disabled") == "true":
                    break
                await page.wait_for_timeout(1200)   # the site rate-limits fast paging
                changed = False
                for _attempt in range(2):       # the first click is sometimes swallowed
                    await nxt.click()
                    for _tick in range(30):
                        await page.wait_for_timeout(500)
                        now = await page.evaluate(_UBER_CARDS)
                        if now and now[0][0] != first:
                            changed = True
                            break
                    if changed:
                        break
                if not changed:
                    if len(out) < 100:
                        raise RuntimeError(f"Uber paging stalled after {len(out)} jobs")
                    logger.warning("[Uber] paging stalled after %d jobs; keeping those", len(out))
                    break
        finally:
            await browser.close()
    return list(out.values())


# ── Meta (needs a real browser: the list is rendered client-side) ────────────

_META_OFFICES = ["Bangalore, India", "Hyderabad, India", "Gurgaon, India", "Mumbai, India",
                 "New Delhi, India"]


async def meta(client: httpx.AsyncClient, co: dict) -> list[dict]:
    from urllib.parse import quote
    from playwright.async_api import async_playwright

    query = "&".join(f"offices[{i}]={quote(o)}" for i, o in enumerate(_META_OFFICES))
    out: dict[str, dict] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page(user_agent=UA, locale="en-IN")
            for number in range(1, 30):
                await page.goto(f"https://www.metacareers.com/jobsearch/?{query}&page={number}",
                                wait_until="domcontentloaded", timeout=60000)
                try:
                    await page.wait_for_selector("a[href*='/profile/job_details/']", timeout=15000)
                except Exception:
                    break
                cards = await page.evaluate(
                    "() => [...document.querySelectorAll(\"a[href*='/profile/job_details/']\")]"
                    ".map(a => [a.href, a.innerText])"
                )
                fresh = 0
                for href, text in cards:
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    url = href.split("?")[0]
                    if not lines or url in out:
                        continue
                    fresh += 1
                    place = next((l for l in lines[1:] if "India" in l), "India")
                    out[url] = {
                        "title": lines[0],
                        "location": place.replace("⋅", ";"),
                        "departments": lines[-1] if len(lines) > 2 else "",
                        "apply_url": url,
                        "india_confirmed": True,
                    }
                if not fresh:
                    break
        finally:
            await browser.close()
    return list(out.values())


FEEDS = {"turbohire": turbohire, "uber": uber, "meta": meta,
         "linkedin": linkedin, "internshala": internshala, "google": google,
         "apple": apple, "pcsx": pcsx}
