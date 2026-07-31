import logging
from bs4 import BeautifulSoup

logger = logging.getLogger("job_aggregator.sap")

async def fetch_sap(client, name="SAP Labs India", base_url="https://jobs.sap.com"):
    # Target software roles in India specifically
    url = f"{base_url}/search/?q=software&locationsearch=India"
    jobs = []
    
    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        rows = soup.select('tr.data-row')
        
        for row in rows:
            title_elem = row.select_one('.jobTitle-link')
            loc_elem = row.select_one('.jobLocation')
            
            if not title_elem:
                continue
                
            title = title_elem.text.strip()
            # Clean up location string (often has zip codes and newlines)
            location = loc_elem.text.strip().replace('\n', ', ') if loc_elem else "India"
            
            href = title_elem['href']
            apply_url = f"{base_url}{href}" if href.startswith('/') else href
            
            jobs.append({
                "company": name,
                "title": title,
                "location": location,
                "type": "N/A",
                "apply_url": apply_url,
                "ats": "sap"
            })
            
        logger.info("[SAP] fetched %d jobs", len(jobs))
        return jobs
    except Exception as exc:
        logger.error("[SAP] error fetching jobs: %s", exc)
        return []
