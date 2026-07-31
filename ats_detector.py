import re
import logging
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Fast-local supported ATS platforms where we can extract the exact slug/tenant
SUPPORTED_PATTERNS = [
    # Greenhouse: boards.greenhouse.io/<slug>
    (re.compile(r"boards\.greenhouse\.io/([^/]+)"), "greenhouse", lambda m: {"slug": m.group(1)}),
    # Lever: jobs.lever.co/<slug>
    (re.compile(r"jobs\.lever\.co/([^/]+)"), "lever", lambda m: {"slug": m.group(1)}),
    # Ashby: jobs.ashbyhq.com/<slug>
    (re.compile(r"jobs\.ashbyhq\.com/([^/]+)"), "ashby", lambda m: {"slug": m.group(1)}),
    # Workday: tenant.wdN.myworkdayjobs.com/site
    (re.compile(r"([a-zA-Z0-9_-]+)\.(wd[0-9]+)\.myworkdayjobs\.com/([^/]+)"), "workday", 
     lambda m: {"tenant": m.group(1), "wd_instance": m.group(2), "site": m.group(3)}),
]

# Unsupported ATS domains (for logging/classification)
UNSUPPORTED_DOMAINS = [
    "icims.com", "successfactors.com", "smartrecruiters.com", "workable.com", 
    "bamboohr.com", "breezy.hr", "recruitee.com", "teamtailor.com", "personio.com", 
    "pinpointhq.com", "ripplingats.com", "freshteam.com", "jobvite.com", "comeet.com",
    "oraclecloud.com", "taleo.net", "adp.com", "dayforcehcm.com", "ultipro.com",
    "paycomonline.net", "paylocity.com", "cornerstoneondemand.com", "jazz.co", 
    "manatal.com", "clearcompany.com", "trakstar.com", "bullhorn.com", "crelate.com",
    "vincere.io", "recruiterflow.com", "vidcruiter.com", "catsone.com", 
    "recruiterbox.com", "newtonsoftware.com", "applicantpro.com", "paycor.com",
    "deel.com", "remote.com", "talentlyft.com", "seekout.com", "occupop.com", "hirehive.com"
]

async def _analyze_url(url: str, client: httpx.AsyncClient) -> dict | None:
    """Check a specific URL (or its redirects) against our patterns."""
    for pattern, ats_type, extractor in SUPPORTED_PATTERNS:
        match = pattern.search(url)
        if match:
            return {"ats": ats_type, **extractor(match)}
            
    # Check unsupported domains
    domain = urlparse(url).netloc
    if any(unsupported in domain for unsupported in UNSUPPORTED_DOMAINS):
        return {"ats": "custom", "reason": f"Unsupported ATS domain: {domain}"}
        
    return None

async def detect_ats(careers_url: str) -> dict:
    """
    Given a generic careers URL, attempt to detect the ATS used.
    Returns a dict with 'ats' and any required connection parameters (slug, tenant, etc.).
    If unable to detect, returns {'ats': 'custom'}.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            # 1. Check the URL itself (it might already be the direct ATS URL)
            result = await _analyze_url(careers_url, client)
            if result:
                return result
                
            # 2. Fetch the page and look for iframes or links to known ATS platforms
            response = await client.get(careers_url)
            response.raise_for_status()
            
            # The final URL after any redirects might be the ATS
            result = await _analyze_url(str(response.url), client)
            if result:
                return result
                
            # 3. Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Check iframes (many companies embed the ATS)
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src")
                if src:
                    result = await _analyze_url(src, client)
                    if result:
                        return result
                        
            # Check links (many companies link out to the ATS)
            for a in soup.find_all("a"):
                href = a.get("href")
                if href:
                    result = await _analyze_url(href, client)
                    if result:
                        return result
                        
    except Exception as exc:
        logger.debug("Failed to detect ATS for %s: %s", careers_url, exc)
        
    return {"ats": "custom"}
