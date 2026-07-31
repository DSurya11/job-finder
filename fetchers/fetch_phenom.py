import httpx
import json
from datetime import datetime, timezone

async def fetch_phenom(client: httpx.AsyncClient, company_name: str, domain: str, lang: str = "en_us", country: str = "us", delay: float = 2.0):
    print(f"Fetching {company_name} (Phenom)...")
    url = f"https://{domain}/widgets"
    
    payload = {
        "lang": lang,
        "deviceType": "desktop",
        "country": country,
        "pageName": "search-results",
        "ddoKey": "refineSearch",
        "from": 0,
        "size": 100,
        "keywords": "software",
        "jobs": True
    }
    
    jobs = []
    try:
        res = await client.post(url, json=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        if res.status_code != 200:
            print(f"[{company_name}] Phenom returned {res.status_code}")
            return jobs
            
        data = res.json()
        search_data = data.get("refineSearch", {}).get("data", {}).get("jobs", [])
        
        for pos in search_data:
            job_id = pos.get("jobId")
            title = pos.get("title")
            location = f"{pos.get('city', '')}, {pos.get('country', '')}".strip(", ")
            
            # Usually phenom jobs are under /jobs/{title-slug}/{jobId} or just /jobs/{jobId}
            # The API often returns the direct ATS URL in applyUrl
            apply_url = pos.get("applyUrl")
            if not apply_url:
                apply_url = f"https://{domain}/jobs/{job_id}"
            
            jobs.append({
                "id": str(job_id),
                "title": title,
                "company": company_name,
                "location": location,
                "apply_url": apply_url,
                "ats_source": "Phenom",
                "date_fetched": datetime.now(timezone.utc).isoformat()
            })
    except Exception as e:
        print(f"[{company_name}] Error fetching Phenom: {e}")
        
    return jobs
