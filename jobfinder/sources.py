"""ATS adapters.

Every adapter is `async fetch(client, company) -> list[dict]` and returns raw
postings with these keys (all optional except title and apply_url):

  title, location, employment_type, description_html, description,
  apply_url, departments, posted_at, salary_struct, detail_url, detail_kind

Adapters raise on failure so the pipeline can record the company as broken
instead of silently reporting zero jobs.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def _iso(value) -> str:
    """Best-effort ISO date from epoch millis or an ISO-ish string."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).strftime("%Y-%m-%d")
    return str(value)[:10]


# ── Greenhouse ───────────────────────────────────────────────────────────────

async def greenhouse(client: httpx.AsyncClient, co: dict) -> list[dict]:
    resp = await client.get(
        f"https://boards-api.greenhouse.io/v1/boards/{co['slug']}/jobs",
        params={"content": "true"}, timeout=40,
    )
    resp.raise_for_status()
    out = []
    for j in resp.json().get("jobs", []):
        offices = ", ".join(o.get("name") or "" for o in j.get("offices") or [])
        location = (j.get("location") or {}).get("name") or ""
        out.append({
            "title": j.get("title", ""),
            # Offices often name the country when the location line is just a city.
            "location": f"{location}; {offices}" if offices and offices != location else location,
            "description_html": j.get("content", ""),
            "apply_url": j.get("absolute_url", ""),
            "departments": ", ".join(d.get("name") or "" for d in j.get("departments") or []),
            "posted_at": _iso(j.get("first_published") or j.get("updated_at")),
        })
    return out


# ── Lever ────────────────────────────────────────────────────────────────────

async def lever(client: httpx.AsyncClient, co: dict) -> list[dict]:
    host = "api.eu.lever.co" if co.get("region") == "eu" else "api.lever.co"
    resp = await client.get(
        f"https://{host}/v0/postings/{co['slug']}", params={"mode": "json"}, timeout=40
    )
    resp.raise_for_status()
    out = []
    for p in resp.json():
        cat = p.get("categories") or {}
        locations = cat.get("allLocations") or [cat.get("location") or ""]
        parts = [p.get("description") or ""]
        for block in p.get("lists") or []:
            parts.append(f"<h3>{block.get('text', '')}</h3><ul>{block.get('content', '')}</ul>")
        parts.append(p.get("additional") or "")
        location = "; ".join(x for x in locations if x)
        if p.get("workplaceType") == "remote" and "remote" not in location.lower():
            location = f"{location} (Remote)"
        out.append({
            "title": p.get("text", ""),
            "location": location,
            "employment_type": cat.get("commitment") or "",
            "description_html": "\n".join(parts),
            "apply_url": p.get("hostedUrl") or p.get("applyUrl") or "",
            "departments": ", ".join(x for x in (cat.get("department"), cat.get("team")) if x),
            "posted_at": _iso(p.get("createdAt")),
            "salary_struct": p.get("salaryRange"),
        })
    return out


# ── Ashby ────────────────────────────────────────────────────────────────────

async def ashby(client: httpx.AsyncClient, co: dict) -> list[dict]:
    resp = await client.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{co['slug']}",
        params={"includeCompensation": "true"}, timeout=40,
    )
    resp.raise_for_status()
    out = []
    for j in resp.json().get("jobs", []):
        locations = [j.get("location") or ""]
        locations += [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        country = ((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")
        if country:
            locations.append(country)
        location = "; ".join(dict.fromkeys(x for x in locations if x))
        if j.get("isRemote") and "remote" not in location.lower():
            location = f"{location} (Remote)"
        comp = (j.get("compensation") or {}).get("compensationTierSummary")
        out.append({
            "title": j.get("title", ""),
            "location": location,
            "employment_type": j.get("employmentType") or "",
            "description_html": j.get("descriptionHtml") or j.get("descriptionPlain") or "",
            "apply_url": j.get("jobUrl") or j.get("applyUrl") or "",
            "departments": ", ".join(x for x in (j.get("department"), j.get("team")) if x),
            "posted_at": _iso(j.get("publishedAt")),
            "salary_struct": {"text": comp} if comp else None,
        })
    return out


# ── SmartRecruiters ──────────────────────────────────────────────────────────

async def smartrecruiters(client: httpx.AsyncClient, co: dict) -> list[dict]:
    slug, out, offset = co["slug"], [], 0
    while True:
        resp = await client.get(
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
            params={"country": "in", "limit": 100, "offset": offset}, timeout=40,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content") or []
        for j in content:
            loc = j.get("location") or {}
            location = loc.get("fullLocation") or ", ".join(
                x for x in (loc.get("city"), loc.get("region"), "India") if x
            )
            if loc.get("remote"):
                location += " (Remote)"
            out.append({
                "title": j.get("name", ""),
                "location": location,
                "employment_type": (j.get("typeOfEmployment") or {}).get("label") or "",
                "apply_url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                "departments": ", ".join(
                    x for x in ((j.get("department") or {}).get("label"),
                                (j.get("function") or {}).get("label")) if x
                ),
                "posted_at": _iso(j.get("releasedDate")),
                "detail_kind": "smartrecruiters",
                "detail_url": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{j.get('id')}",
            })
        offset += len(content)
        if not content or offset >= (data.get("totalFound") or 0):
            return out


# ── Workable ─────────────────────────────────────────────────────────────────

async def workable(client: httpx.AsyncClient, co: dict) -> list[dict]:
    resp = await client.get(
        f"https://apply.workable.com/api/v1/widget/accounts/{co['slug']}",
        params={"details": "true"}, timeout=40,
    )
    resp.raise_for_status()
    out = []
    for j in resp.json().get("jobs", []):
        location = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        if j.get("telecommuting"):
            location = f"{location} (Remote)" if location else "Remote"
        out.append({
            "title": j.get("title", ""),
            "location": location,
            "employment_type": j.get("employment_type") or "",
            "description_html": j.get("description") or "",
            "apply_url": j.get("url") or j.get("application_url") or "",
            "departments": j.get("department") or "",
            "posted_at": _iso(j.get("published_on") or j.get("created_at")),
        })
    return out


# ── Recruitee ────────────────────────────────────────────────────────────────

async def recruitee(client: httpx.AsyncClient, co: dict) -> list[dict]:
    resp = await client.get(f"https://{co['slug']}.recruitee.com/api/offers/", timeout=40)
    resp.raise_for_status()
    out = []
    for j in resp.json().get("offers", []):
        location = j.get("location") or ", ".join(
            x for x in (j.get("city"), j.get("country")) if x
        )
        if j.get("remote") and "remote" not in location.lower():
            location = f"{location} (Remote)"
        salary = j.get("salary") or {}
        out.append({
            "title": j.get("title", ""),
            "location": location,
            "employment_type": j.get("employment_type_code") or "",
            "description_html": f"{j.get('description') or ''}\n{j.get('requirements') or ''}",
            "apply_url": j.get("careers_url") or "",
            "departments": j.get("department") or "",
            "posted_at": _iso(j.get("published_at") or j.get("created_at")),
            "salary_struct": {
                "min": float(salary["min"]) if salary.get("min") else None,
                "max": float(salary["max"]) if salary.get("max") else None,
                "currency": salary.get("currency"), "interval": salary.get("period"),
            } if salary else None,
        })
    return out


# ── Workday ──────────────────────────────────────────────────────────────────

def _india_facets(facets: list) -> list[tuple[str, list[str]]]:
    """The facet selections that mean 'India' on this tenant, most promising first.

    The parameter name and ids vary per tenant, so they are read from the
    tenant's own facet list: a country-level "India" value when there is one,
    then each location facet's values that are Indian places. Several are
    returned because a tenant can list a facet that selects nothing when applied.
    """
    from .enrich import locate

    country: tuple[str, list[str]] | None = None
    sites: dict[str, list[str]] = {}

    def walk(nodes: list, parent: str | None) -> None:
        nonlocal country
        for f in nodes or []:
            param = f.get("facetParameter") or parent
            for v in f.get("values") or []:
                if "values" in v:
                    walk([v], param)
                    continue
                name = (v.get("descriptor") or "").strip()
                if name.lower() == "india" and country is None:
                    country = (param, [v["id"]])
                elif locate(name)["scope"] == "india":
                    sites.setdefault(param, []).append(v["id"])

    walk(facets, None)
    ranked = sorted(sites.items(), key=lambda kv: -len(kv[1]))
    return ([country] if country else []) + ranked


async def workday(client: httpx.AsyncClient, co: dict) -> list[dict]:
    base = f"https://{co['tenant']}.{co['wd_instance']}.myworkdayjobs.com"
    site = co["site"]
    api = f"{base}/wday/cxs/{co['tenant']}/{site}"
    headers = {
        "Accept": "application/json", "Content-Type": "application/json",
        "User-Agent": UA, "Origin": base, "Referer": f"{base}/{site}",
    }
    delay = float(co.get("delay", 0.6))

    async def page(body: dict) -> dict:
        for attempt in range(4):
            resp = await client.post(f"{api}/jobs", json=body, headers=headers, timeout=40)
            if resp.status_code in (403, 429, 500, 502, 503) and attempt < 3:
                await asyncio.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")

    first = await page({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""})
    searches = [{"appliedFacets": {param: ids}, "searchText": ""}
                for param, ids in _india_facets(first.get("facets") or [])]
    # Last resort, and the only one on a tenant with no location facet: text search,
    # letting the location classifier drop the non-India matches.
    searches.append({"appliedFacets": {}, "searchText": "India"})

    # The first search that finds anything is used. Baker Hughes, for one, lists a
    # city facet that selects nothing when applied, beside a state facet that works.
    body, data, total = searches[0], {}, 0
    for body in searches:
        data = await page({**body, "limit": 20, "offset": 0})
        total = data.get("total") or 0
        if total:
            break
    facet = bool(body["appliedFacets"])
    if not facet:
        logger.info("[Workday/%s] no usable India facet, using text search", co["name"])

    out, offset = [], 0
    while True:
        postings = data.get("jobPostings") or []
        for p in postings:
            path = p.get("externalPath") or ""
            if not path:
                continue
            out.append({
                "title": p.get("title", ""),
                "location": p.get("locationsText") or "",
                "apply_url": f"{base}/{site}{path}",
                "posted_at": "",
                "posted_text": p.get("postedOn") or "",
                "detail_kind": "workday",
                "detail_url": f"{api}{path}",
                # The facet already guarantees India even when the location
                # line only says "3 Locations".
                "india_confirmed": bool(facet),
            })
        offset += len(postings)
        if not postings or offset >= total or offset >= 4000:
            return out
        await asyncio.sleep(delay)
        data = await page({**body, "limit": 20, "offset": offset})


# ── Atlassian (own listing endpoint) ─────────────────────────────────────────

async def atlassian(client: httpx.AsyncClient, co: dict) -> list[dict]:
    resp = await client.get(
        "https://www.atlassian.com/endpoint/careers/listings",
        headers={"User-Agent": UA}, timeout=60,
    )
    resp.raise_for_status()
    out = []
    for j in resp.json():
        portal = j.get("portalJobPost") or {}
        html = "\n".join(
            j.get(k) or "" for k in ("overview", "responsibilities", "qualifications")
        )
        out.append({
            "title": j.get("title", ""),
            "location": "; ".join(j.get("locations") or []),
            "employment_type": j.get("type") or "",
            "description_html": html,
            "apply_url": portal.get("portalUrl")
            or f"https://www.atlassian.com/company/careers/details/{j.get('id')}",
            "departments": j.get("category") or "",
            "posted_at": _iso(portal.get("updatedDate")),
        })
    return out


# ── Zerodha (own listing endpoint) ───────────────────────────────────────────

async def zerodha(client: httpx.AsyncClient, co: dict) -> list[dict]:
    base = "https://careers.zerodha.com"
    resp = await client.get(f"{base}/api/jobs", headers={"User-Agent": UA}, timeout=40)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError("Zerodha jobs endpoint reported failure")
    out = []
    for j in data.get("data") or []:
        location = j.get("location") or ""
        if "remote" in (j.get("location_type") or "").lower():
            location += " (Remote)"
        out.append({
            "title": j.get("job_title") or "",
            "location": location,
            "description_html": j.get("description") or "",
            # The site has no page per job; applications go through a form on
            # the listing, so the fragment only keeps each posting's URL unique.
            "apply_url": f"{base}/#{j.get('name')}",
        })
    return out


# ── Legacy fetchers kept from the first version of this project ──────────────

def _legacy(jobs: list[dict]) -> list[dict]:
    out = []
    for j in jobs or []:
        out.append({
            "title": j.get("title", ""),
            "location": j.get("location", ""),
            "employment_type": j.get("employment_type", ""),
            "description_html": j.get("raw_content") or "",
            "description": j.get("description", ""),
            "apply_url": j.get("apply_url") or j.get("url") or "",
            "departments": j.get("departments", ""),
            "posted_at": _iso(j.get("posted_at") or j.get("date_posted")),
        })
    return out


async def amazon(client, co):
    from fetchers.fetch_amazon import fetch_amazon
    return _legacy(await fetch_amazon(client, delay=1.0))


async def swiggy(client, co):
    from fetchers.fetch_swiggy import fetch_swiggy_jobs
    return _legacy(await fetch_swiggy_jobs(client, co))


async def eightfold(client, co):
    from fetchers.fetch_eightfold import fetch_eightfold
    return _legacy(await fetch_eightfold(client, co["name"], co["slug"]))


async def phenom(client, co):
    from fetchers.fetch_phenom import fetch_phenom
    return _legacy(await fetch_phenom(
        client, co["name"], co["slug"], co.get("lang", "en_us"), co.get("country", "us")
    ))


async def servicenow(client, co):
    from fetchers.fetch_servicenow import fetch_servicenow
    return _legacy(await fetch_servicenow(
        client, co["name"], co.get("careers_url", "https://careers.servicenow.com")
    ))


async def oracle(client, co):
    from fetchers.fetch_oracle import fetch_oracle_jobs
    return _legacy(await asyncio.to_thread(fetch_oracle_jobs, [co]))


async def gs_graphql(client, co):
    from fetchers.fetch_gs import fetch_gs_jobs
    return _legacy(await asyncio.to_thread(fetch_gs_jobs, co["name"]))


async def dom_scraper(client, co):
    from fetchers.fetch_dom import fetch_all_dom
    return _legacy(await fetch_all_dom([co]))


ADAPTERS = {
    "greenhouse": greenhouse, "lever": lever, "ashby": ashby,
    "smartrecruiters": smartrecruiters, "workable": workable, "recruitee": recruitee,
    "workday": workday, "atlassian": atlassian, "zerodha": zerodha,
    "amazon": amazon, "swiggy": swiggy, "eightfold": eightfold, "phenom": phenom,
    "servicenow": servicenow,
    "oracle": oracle, "gs_graphql": gs_graphql, "dom_scraper": dom_scraper,
}

# Requests in flight per ATS host family; Workday tenants are separate hosts
# but share bot protection, so they stay modest.
CONCURRENCY = {
    "greenhouse": 10, "ashby": 8, "lever": 3, "smartrecruiters": 4, "workable": 3,
    "recruitee": 4, "workday": 6, "dom_scraper": 1, "linkedin": 1, "internshala": 1,
}
