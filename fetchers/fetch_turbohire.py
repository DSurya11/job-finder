import httpx
import json
from datetime import datetime, timezone

async def fetch_turbohire(client: httpx.AsyncClient, company_name: str, org_id: str, delay: float = 2.0):
    print(f"Fetching {company_name} (Turbohire)...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Origin': 'https://olacareers.turbohire.co',
        'Referer': 'https://olacareers.turbohire.co/'
    }
    
    jobs = []
    try:
        # Step 1: Get token
        token_url = f"https://thapi.azurewebsites.net/api/token/noauth?orgId={org_id}"
        res_token = await client.get(token_url, headers=headers, timeout=15)
        if res_token.status_code != 200:
            print(f"[{company_name}] Turbohire token fetch failed: {res_token.status_code}")
            return jobs
            
        token = res_token.json().get("access_token")
        if not token:
            print(f"[{company_name}] Turbohire missing access_token")
            return jobs
            
        # Step 2: Fetch jobs
        headers["Authorization"] = f"Bearer {token}"
        jobs_url = f"https://thapi.azurewebsites.net/api/careerpagev2/filteredjobs?orgId={org_id}&pageType=0"
        
        payload = {
            "searchtext": "",
            "jobType": [],
            "department": [],
            "location": [],
            "experience": []
        }
        
        res_jobs = await client.post(jobs_url, json=payload, headers=headers, timeout=15)
        if res_jobs.status_code != 200:
            print(f"[{company_name}] Turbohire jobs fetch failed: {res_jobs.status_code}")
            return jobs
            
        data = res_jobs.json()
        positions = data.get("Result", [])
        
        for pos in positions:
            job_id = pos.get("JobId")
            title = pos.get("JobTitle")
            location = pos.get("JobLocation", "")
            
            # Apply URL is usually the dashboard URL with a specific job param
            apply_url = f"https://olacareers.turbohire.co/job/{job_id}"
            
            jobs.append({
                "id": str(job_id),
                "title": title,
                "company": company_name,
                "location": location,
                "apply_url": apply_url,
                "ats_source": "Turbohire",
                "date_fetched": datetime.now(timezone.utc).isoformat()
            })
    except Exception as e:
        print(f"[{company_name}] Error fetching Turbohire: {e}")
        
    return jobs
