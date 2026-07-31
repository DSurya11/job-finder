import logging
import asyncio
import os
from apify_client import ApifyClientAsync
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_API_TOKEN")

# Simple pageFunctions for each company to extract Title, Location, and URL.
# Note: Custom ATS HTML is highly dynamic. These selectors may require updates if the site changes.

GOOGLE_PAGE_FUNCTION = """
async ({ page, request }) => {
    // Wait for the jobs to load (using the class seen in the screenshot)
    await page.waitForSelector('.sMn82b', { timeout: 10000 }).catch(() => {});
    
    return await page.evaluate(() => {
        const jobs = [];
        document.querySelectorAll('.sMn82b').forEach(el => {
            const text = el.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            
            // Expected: ["Facilities Manager, Data Center...", "Google | Frankfurt...", "Learn more"]
            if (lines.length >= 2) {
                const title = lines[0];
                let location = lines[1];
                if (location.startsWith('Google |')) {
                    location = location.replace('Google |', '').trim();
                }
                
                // Try to find the link, which might be in a parent or an internal a tag
                let link = '';
                const aTag = el.querySelector('a') || el.closest('a');
                if (aTag) {
                    link = aTag.href;
                }
                
                if (title) {
                    jobs.push({
                        company: "Google",
                        title,
                        location,
                        url: link,
                        description: "",
                        employment_type: "Full-time"
                    });
                }
            }
        });
        return jobs;
    });
}
"""

MICROSOFT_PAGE_FUNCTION = """
async ({ page, request }) => {
    // Wait for the job list to load (using the specific 'a' tag class seen in the screenshot)
    await page.waitForSelector('a[aria-label^="View job:"]', { timeout: 10000 }).catch(() => {});
    
    return await page.evaluate(() => {
        const jobs = [];
        document.querySelectorAll('a[aria-label^="View job:"]').forEach(el => {
            let title = el.getAttribute('aria-label') || '';
            title = title.replace('View job:', '').trim();
            
            const link = el.href || '';
            
            const text = el.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            // Typically: [ "Senior Software Engineer", "India, Multiple Locations...", "Posted 2 days ago" ]
            const location = lines.length > 1 ? lines[1] : '';
            
            if (title) {
                jobs.push({
                    company: "Microsoft",
                    title,
                    location,
                    url: link,
                    description: "",
                    employment_type: "Full-time"
                });
            }
        });
        return jobs;
    });
}
"""

FLIPKART_PAGE_FUNCTION = """
async ({ page, request }) => {
    await page.waitForSelector('.job-row', { timeout: 10000 }).catch(() => {});
    return await page.evaluate(() => {
        const jobs = [];
        document.querySelectorAll('.job-row').forEach(el => {
            const title = el.querySelector('.job-title')?.innerText || '';
            const location = el.querySelector('.job-location')?.innerText || '';
            const link = el.querySelector('a')?.href || '';
            
            if (title) {
                jobs.push({
                    company: "Flipkart",
                    title,
                    location,
                    url: link,
                    description: "",
                    employment_type: "Full-time"
                });
            }
        });
        return jobs;
    });
}
"""

SALESFORCE_PAGE_FUNCTION = """
async ({ page, request }) => {
    await new Promise(r => setTimeout(r, 5000));
    return await page.evaluate(() => {
        const jobs = [];
        document.querySelectorAll('.job-title').forEach(el => {
            const aTag = el.querySelector('a') || el.closest('a') || el;
            const title = aTag.innerText || el.innerText || '';
            const link = aTag.href || '';
            if (title && link) {
                jobs.push({ title: title.trim(), url: link });
            }
        });
        return jobs;
    });
}
"""

GENERIC_PAGE_FUNCTION = """
async ({ page, request }) => {
    await new Promise(r => setTimeout(r, 5000));
    return await page.evaluate(() => {
        const jobs = [];
        const seen = new Set();
        document.querySelectorAll('a').forEach(a => {
            const href = a.href || '';
            const text = a.innerText || '';
            const hrefLower = href.toLowerCase();
            if (text.trim() && text.trim().length > 5 && (hrefLower.includes('job') || hrefLower.includes('req') || hrefLower.includes('career'))) {
                if (hrefLower.endsWith('/jobs') || hrefLower.endsWith('/careers') || hrefLower.includes('search')) return;
                if (!seen.has(href)) {
                    seen.add(href);
                    jobs.push({ title: text.split('\\n')[0].trim(), url: href });
                }
            }
        });
        // PhenomPeople fallback
        if (jobs.length === 0) {
            document.querySelectorAll('.job-title, .job-innerwrap, .job-title-link, [data-ph-id]').forEach(el => {
                const a = el.querySelector('a') || el.closest('a') || el;
                if (a && a.href && !seen.has(a.href) && a.innerText.trim()) {
                    seen.add(a.href);
                    jobs.push({ title: a.innerText.split('\\n')[0].trim(), url: a.href });
                }
            });
        }
        return jobs;
    });
}
"""

async def run_puppeteer_scraper(client: ApifyClientAsync, start_url: str, page_function: str) -> list[dict]:
    """Run the apify/puppeteer-scraper actor and return the results."""
    run_input = {
        "startUrls": [{"url": start_url}],
        "pageFunction": page_function,
        "proxyConfiguration": {"useApifyProxy": True},
        "preNavigationHooks": "",
        "postNavigationHooks": "",
        "initialCookies": [],
        "waitUntil": ["networkidle2"]
    }
    
    logger.info("[Apify] Starting puppeteer-scraper for %s", start_url)
    run = await client.actor("apify/puppeteer-scraper").call(run_input=run_input)
    
    results = []
    async for item in client.dataset(run.default_dataset_id).iterate_items():
        if isinstance(item, list):
            results.extend(item)
        elif isinstance(item, dict) and "title" in item:
            results.append(item)
            
    return results

def _normalise(job: dict, company_name: str) -> dict:
    return {
        "company": company_name,
        "title": job.get("title", ""),
        "location": job.get("location", ""),
        "employment_type": job.get("employment_type", "Full-time"),
        "ats_source": "Apify",
        "apply_url": job.get("url", ""),
        "description": job.get("description", ""),
        "departments": "",
        "date_fetched": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }

async def fetch_apify(company_name: str, careers_url: str) -> list[dict]:
    """Fetch jobs for a custom company using Apify's Puppeteer Scraper."""
    if not APIFY_TOKEN or APIFY_TOKEN == "your_token_here":
        logger.warning("[Apify] Missing APIFY_API_TOKEN in .env. Skipping %s.", company_name)
        return []
        
    client = ApifyClientAsync(APIFY_TOKEN)
    
    if company_name == "Google":
        raw = await run_puppeteer_scraper(client, careers_url, GOOGLE_PAGE_FUNCTION)
    elif company_name == "Microsoft":
        raw = await run_puppeteer_scraper(client, careers_url, MICROSOFT_PAGE_FUNCTION)
    elif company_name == "Flipkart":
        raw = await run_puppeteer_scraper(client, careers_url, FLIPKART_PAGE_FUNCTION)
    elif company_name == "Salesforce":
        raw = await run_puppeteer_scraper(client, "https://careers.salesforce.com/en/jobs/?search=&country=India&pagesize=20#results", SALESFORCE_PAGE_FUNCTION)
    elif company_name in ["Mastercard", "Cisco", "PayPal"]:
        raw = await run_puppeteer_scraper(client, careers_url, GENERIC_PAGE_FUNCTION)
    else:
        logger.warning("[Apify] No custom pageFunction written for %s yet.", company_name)
        return []
        
    jobs = [_normalise(j, company_name) for j in raw]
    logger.info("[Apify/%s] fetched %d jobs", company_name, len(jobs))
    return jobs
