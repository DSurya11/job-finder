import httpx
import json
from datetime import datetime, timezone

async def fetch_eightfold(client: httpx.AsyncClient, company_name: str, domain: str, delay: float = 2.0):
    print(f"Fetching {company_name} (Eightfold)...")
    url = f"https://{domain}.eightfold.ai/api/pcsx/search?domain={domain}.com&query=software&start=0&num=100"
    
    jobs = []
    try:
        res = await client.get(url, timeout=15)
        if res.status_code != 200:
            print(f"[{company_name}] Eightfold returned {res.status_code}")
            return jobs
            
        data = res.json()
        positions = data.get("data", {}).get("positions", [])
        
        for pos in positions:
            job_id = pos.get("id")
            title = pos.get("name")
            location = pos.get("location", "")
            if not location and "locations" in pos and pos["locations"]:
                location = pos["locations"][0]
            
            # Form ATS URL
            apply_url = f"https://{domain}.eightfold.ai/careers?query={job_id}"
            
            jobs.append({
                "id": str(job_id),
                "title": title,
                "company": company_name,
                "location": location,
                "apply_url": apply_url,
                "ats_source": "Eightfold AI",
                "date_fetched": datetime.now(timezone.utc).isoformat()
            })
    except Exception as e:
        print(f"[{company_name}] Error fetching Eightfold: {e}")
        
    return jobs
