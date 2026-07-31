import httpx
import logging
from datetime import datetime, timezone
import re
import asyncio

logger = logging.getLogger("fetchers.fetch_sitemap")

async def fetch_sitemap_jobs(client: httpx.AsyncClient, company_info: dict) -> list[dict]:
    name = company_info["name"]
    sitemap_url = company_info.get("sitemap_url")
    if not sitemap_url:
        logger.error(f"[{name}] missing sitemap_url")
        return []

    jobs = []
    try:
        response = await client.get(sitemap_url, timeout=30.0)
        response.raise_for_status()
        
        text = response.text
        urls = re.findall(r'<loc>(.*?)</loc>', text)
        
        job_urls = [u for u in urls if ('/jobs/R-' in u or '/job/' in u) and '/us/en/' not in u]
        logger.info(f"[{name}] Found {len(job_urls)} potential job URLs in sitemap")
        
        # We limit concurrency so we don't DOS the site
        semaphore = asyncio.Semaphore(50)
        
        async def fetch_page(url, session_client):
            async with semaphore:
                try:
                    r = await session_client.get(url, timeout=10.0)
                    title_match = re.search(r'<title>(.*?)</title>', r.text, re.IGNORECASE)
                    title = title_match.group(1) if title_match else ""
                    
                    if not title or ("software" not in title.lower() and "engineer" not in title.lower() and "sde" not in title.lower() and "developer" not in title.lower()):
                        return None
                    
                    # Try JSON-LD addressRegion first, then addressLocality
                    loc_match = re.search(r'"addressRegion":"([^"]+)"', r.text)
                    if not loc_match:
                        loc_match = re.search(r'"addressLocality":"([^"]+)"', r.text)
                    location = loc_match.group(1) if loc_match else ""
                    
                    # If we can't determine location, skip rather than assuming India
                    if not location:
                        return None
                        
                    return {
                        "company": name,
                        "title": title.replace(" - Walmart Careers", "").strip(),
                        "location": location,
                        "apply_url": url,
                        "ats_source": "Sitemap Scraper",
                        "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "description": ""
                    }
                except:
                    return None

        # Sample every 5th URL across the full list to get broad coverage
        # rather than only scanning the first N entries (which skews toward
        # whichever role types happen to be at the front of the sitemap).
        sampled_urls = job_urls[::5]
        logger.info(f"[{name}] Sampling {len(sampled_urls)} of {len(job_urls)} URLs (every 5th)")
        
        chunk_size = 1000
        async with httpx.AsyncClient(verify=False) as session_client:
            for i in range(0, len(sampled_urls), chunk_size):
                chunk = sampled_urls[i:i+chunk_size]
                results = await asyncio.gather(*[fetch_page(u, session_client) for u in chunk])
                for res in results:
                    if res:
                        jobs.append(res)
                logger.info(f"[{name}] Processed {min(i+chunk_size, len(sampled_urls))}/{len(sampled_urls)} sampled URLs")
            
    except Exception as e:
        logger.error(f"[{name}] failed: {e}")
        
    logger.info(f"[{name}] fetched {len(jobs)} jobs")
    return jobs
