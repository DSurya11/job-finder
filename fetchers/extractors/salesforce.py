import logging

logger = logging.getLogger("job_aggregator.dom.salesforce")

async def extract_jobs(page, url, name):
    jobs = []
    logger.info("Extracting Salesforce jobs from %s", url)
    
    # Salesforce WAF often blocks us, we might need a longer wait or human-like interaction
    search_url = "https://careers.salesforce.com/en/jobs/?search=&country=India&pagesize=20#results"
    
    try:
        await page.goto(search_url, wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        # If there's an iframe, we might need to search it, but usually WAF just blocks the main page
        title_elements = await page.query_selector_all(".job-title")
        for el in title_elements:
            a_tag = await el.query_selector("a")
            if not a_tag: a_tag = el
            
            title = await a_tag.inner_text()
            href = await a_tag.get_attribute("href")
            if title and href:
                full_url = href if href.startswith("http") else "https://careers.salesforce.com" + href
                jobs.append({
                    "company": name,
                    "title": title.strip(),
                    "url": full_url
                })
    except Exception as e:
        logger.error("Salesforce extraction failed: %s", e)
            
    logger.info("Salesforce: Found %d jobs", len(jobs))
    return jobs
