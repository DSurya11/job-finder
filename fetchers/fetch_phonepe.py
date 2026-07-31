import logging

logger = logging.getLogger("job_aggregator.phonepe")

async def fetch_phonepe(client, name="PhonePe"):
    url = "https://www.phonepe.com/webstatic/14536/page-data/careers/job-openings/page-data.json"
    jobs = []
    
    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        
        edges = data.get("result", {}).get("data", {}).get("allJobPostings", {}).get("edges", [])
        
        for edge in edges:
            node = edge.get("node", {})
            title = node.get("title", "")
            location = node.get("location", "")
            # PhonePe jobs link
            slug = node.get("id", "")
            apply_url = f"https://www.phonepe.com/careers/job-openings/{slug}" if slug else ""
            
            jobs.append({
                "company": name,
                "title": title,
                "location": location,
                "type": "N/A",
                "apply_url": apply_url,
                "ats": "phonepe"
            })
            
        logger.info("[PhonePe] fetched %d jobs", len(jobs))
        return jobs
    except Exception as exc:
        logger.error("[PhonePe] error fetching jobs: %s", exc)
        return []
