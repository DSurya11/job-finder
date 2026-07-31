import logging
from datetime import datetime, timezone

logger = logging.getLogger("job_aggregator.dom.zerodha")

async def extract_jobs(page, url, name):
    jobs = []
    logger.info("Extracting Zerodha jobs from %s", url)
    await page.goto(url, wait_until="networkidle")
    
    await page.wait_for_timeout(3000)
    
    elements = await page.query_selector_all("a")
    seen = set()
    for el in elements:
        href = await el.get_attribute("href")
        if not href: continue
        
        text = await el.inner_text()
        if not text.strip(): continue
        
        href_lower = href.lower()
        if "job" in href_lower or "opening" in href_lower or "career" in href_lower:
            if href.strip("/") in ["https://careers.zerodha.com", "/"]: continue
            
            full_url = href if href.startswith("http") else url.rstrip("/") + href
            if full_url not in seen:
                seen.add(full_url)
                jobs.append({
                    "company": name,
                    "title": text.strip(),
                    "apply_url": full_url,
                    "ats_source": "DOM Scraper",
                    "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    "location": "India"
                })
            
    logger.info("Zerodha: Found %d potential job links", len(jobs))
    return jobs
