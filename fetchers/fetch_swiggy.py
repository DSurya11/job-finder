import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger("fetchers.fetch_swiggy")

async def fetch_swiggy_jobs(client: httpx.AsyncClient, company_info: dict) -> list[dict]:
    name = company_info["name"]
    url = "https://swiggy.mynexthire.com/employer/careers/reqlist/get"
    
    payload = {
        "source": "careers",
        "code": "",
        "filterByBuId": -1
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    try:
        response = await client.post(url, json=payload, headers=headers, timeout=15.0)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"[Swiggy] failed: {e}")
        return []

    jobs = []
    items = data.get("reqDetailsBOList", [])
    
    for item in items:
        title = item.get("reqTitle")
        if not title:
            continue
            
        location = item.get("locationAddress") or item.get("location") or "India"
        req_id = item.get("reqId")
        
        # MyNextHire does not support deep linking externally, it redirects or shows a generic table.
        # Direct them to the main careers site.
        apply_url = f"https://careers.swiggy.com/"
        description = item.get("jdDisplay", "")
        
        jobs.append({
            "company": name,
            "title": title.strip(),
            "location": location.strip(),
            "apply_url": apply_url,
            "ats_source": "Swiggy API",
            "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "description": description
        })

    logger.info(f"[Swiggy] fetched {len(jobs)} jobs")
    return jobs
