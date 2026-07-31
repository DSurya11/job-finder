import logging
from datetime import datetime, timezone

logger = logging.getLogger("job_aggregator.dom.deshaw")

async def extract_jobs(page, url, name):
    jobs = []
    logger.info("Extracting DE Shaw jobs from %s", url)
    target_url = "https://www.deshawindia.com/careers/job-openings"
    await page.goto(target_url, wait_until="networkidle")
    
    await page.wait_for_timeout(3000)
    
    elements = await page.query_selector_all("a[href*='/careers/']")
    seen = set()
    for el in elements:
        href = await el.get_attribute("href")
        if not href: continue
        
        # Check if URL ends with digits (job id) e.g. -5423
        if not href.split('-')[-1].isdigit():
            continue
            
        text = await el.inner_text()
        if not text.strip(): continue
        
        # Typical format: "iconLead, Tech (QTE): We are looking for..."
        parts = text.split(":")
        title = parts[0].replace("icon", "").strip()
        
        full_url = href if href.startswith("http") else "https://www.deshawindia.com" + href
        
        if full_url not in seen:
            seen.add(full_url)
            jobs.append({
                "company": name,
                "title": title,
                "apply_url": full_url,
                "ats_source": "DOM Scraper",
                "date_fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "location": "India"
            })
            
    logger.info("DE Shaw: Found %d jobs", len(jobs))
    return jobs
