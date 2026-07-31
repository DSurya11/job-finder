import logging
import asyncio
from playwright.async_api import async_playwright
import importlib

logger = logging.getLogger("job_aggregator.dom_scraper")

async def fetch_all_dom(companies):
    """
    Launch a single Playwright browser context and scrape all companies
    that require direct DOM extraction.
    """
    jobs = []
    
    async with async_playwright() as p:
        # Launch browser once
        browser = await p.chromium.launch(headless=True)
        # Use a realistic User-Agent to avoid basic bot blocks
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        for co in companies:
            name = co["name"]
            url = co.get("careers_url")
            if not url:
                continue
                
            logger.info("[DOM Scraper] Fetching %s...", name)
            
            # Map company name to extractor module (e.g. "DE Shaw" -> "deshaw")
            module_name = name.lower().replace(" ", "").replace("-", "")
            try:
                # Dynamically load the extractor
                extractor = importlib.import_module(f"fetchers.extractors.{module_name}")
                page = await context.new_page()
                
                co_jobs = await extractor.extract_jobs(page, url, name)
                jobs.extend(co_jobs)
                
                await page.close()
                
                # Sleep briefly between companies to be polite
                await asyncio.sleep(2)
                
            except ImportError:
                logger.error("[DOM Scraper] No extractor found for %s (expected fetchers.extractors.%s)", name, module_name)
            except Exception as exc:
                logger.error("[DOM Scraper] Error scraping %s: %s", name, exc)
                
        await browser.close()
        
    return jobs
