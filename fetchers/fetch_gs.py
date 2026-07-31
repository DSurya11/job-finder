import httpx
import logging
from datetime import datetime, timezone

logger = logging.getLogger("fetchers.fetch_gs")

def fetch_gs_jobs(name: str) -> list[dict]:
    """Fetch jobs from Goldman Sachs GraphQL API"""
    url = "https://api-higher.gs.com/gateway/api/v1/graphql"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "*/*"
    }
    
    query = """
    query GetRoles($searchQueryInput: RoleSearchQueryInput!) {
      roleSearch(searchQueryInput: $searchQueryInput) {
        totalCount
        items {
          roleId
          corporateTitle
          jobTitle
          externalSource {
            sourceId
          }
          locations {
            primary
            state
            country
            city
          }
        }
      }
    }
    """
    
    jobs = []
    page = 0
    page_size = 100
    
    with httpx.Client() as client:
        while True:
            payload = {
                'operationName': 'GetRoles',
                'variables': {
                    'searchQueryInput': {
                        'page': {'pageSize': page_size, 'pageNumber': page},
                        'sort': {'sortStrategy': 'RELEVANCE', 'sortOrder': 'DESC'},
                        'filters': [],
                        'experiences': ['PROFESSIONAL'],
                        'searchTerm': ''
                    }
                },
                'query': query
            }
            
            try:
                resp = client.post(url, json=payload, headers=headers, timeout=30.0)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"[Goldman Sachs] Error fetching page {page}: {e}")
                break
                
            items = data.get('data', {}).get('roleSearch', {}).get('items', [])
            if not items:
                break
                
            for item in items:
                job_id = item.get('roleId')
                source_id = item.get('externalSource', {}).get('sourceId')
                title = item.get('jobTitle', '')
                
                # Combine locations
                locs = []
                for l in item.get('locations', []):
                    city = l.get('city')
                    country = l.get('country')
                    if city and country:
                        locs.append(f"{city}, {country}")
                    elif city:
                        locs.append(city)
                        
                loc_str = " | ".join(locs) if locs else "India"
                
                # Use source_id for url if available, otherwise fallback to role_id
                url_id = source_id if source_id else job_id
                job_url = f"https://higher.gs.com/roles/{url_id}"
                
                jobs.append({
                    "id": str(job_id),
                    "title": title,
                    "company": name,
                    "location": loc_str,
                    "apply_url": job_url,
                    "ats_source": "GS GraphQL",
                    "date_fetched": datetime.now().strftime("%Y-%m-%d")
                })
                
            logger.info(f"[Goldman Sachs] Fetched {len(items)} jobs on page {page}")
            if len(items) < page_size:
                break
            
            page += 1
            
    logger.info(f"[Goldman Sachs] Total jobs fetched: {len(jobs)}")
    return jobs
