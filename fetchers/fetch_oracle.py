import httpx
import logging
from typing import List, Dict
from datetime import datetime

logger = logging.getLogger("job_aggregator.oracle")

def fetch_oracle_jobs(companies: List[Dict]) -> List[Dict]:
    """
    Fetch jobs from Oracle Cloud HCM recruiting APIs.
    Requires 'oracle_site_id' (e.g., 'CX_1001') and 'oracle_url' in company config.
    """
    jobs = []
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json'
    }

    with httpx.Client(verify=False, timeout=20.0) as client:
        for co in companies:
            name = co["name"]
            url = co.get("oracle_url")
            site_id = co.get("oracle_site_id")
            
            if not url or not site_id:
                logger.error(f"[Oracle] Missing config for {name}")
                continue
                
            logger.info(f"[Oracle] Fetching {name}...")
            
            offset = 0
            seen_ids = set()
            while True:
                api_url = f"{url}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList.secondaryLocations,flexFieldsFacet.values&finder=findReqs;siteNumber={site_id},keyword=software,location=India&offset={offset}"
                
                success = False
                for attempt in range(3):
                    try:
                        resp = client.get(api_url, headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        success = True
                        break
                    except Exception as e:
                        logger.warning(f"[Oracle] Error on attempt {attempt+1} for {name} at offset {offset}: {e}")
                        import time
                        time.sleep(2)
                
                if not success:
                    logger.error(f"[Oracle] Failed to fetch {name} at offset {offset} after 3 attempts")
                    break

                items = data.get('items', [])
                if items:
                    reqs = items[0].get('requisitionList', [])
                    if not reqs:
                        break
                    new_jobs_added = 0
                    for r in reqs:
                        job_id = str(r.get('Id'))
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)
                        new_jobs_added += 1
                        
                        title = r.get('Title', '')
                        loc = r.get('PrimaryLocation', 'India')
                        job_url = f"{url}/hcmUI/CandidateExperience/en/sites/{site_id}/job/{job_id}"
                        
                        jobs.append({
                            "id": job_id,
                            "title": title,
                            "company": name,
                            "location": loc,
                            "apply_url": job_url,
                            "ats_source": "Oracle Cloud HCM",
                            "date_fetched": datetime.now().strftime("%Y-%m-%d")
                        })
                    
                    if new_jobs_added == 0:
                        logger.info(f"[Oracle] No new jobs found at offset {offset}, terminating pagination")
                        break
                        
                    logger.info(f"[Oracle] Added {new_jobs_added} jobs for {name} (offset {offset})")
                    offset += len(reqs)
                else:
                    break
                
    return jobs
