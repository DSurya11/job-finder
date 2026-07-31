import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger("job_aggregator.servicenow")

async def fetch_servicenow(client, name="ServiceNow", base_url="https://careers.servicenow.com"):
    """
    ServiceNow blocks native API requests via Cloudflare WAF.
    However, their public SEO sitemap.xml exposes all job URLs natively.
    We parse the sitemap to extract job listings without hitting the protected API.
    """
    sitemap_url = f"{base_url}/sitemap.xml"
    jobs = []
    
    try:
        resp = await client.get(sitemap_url, timeout=15.0)
        resp.raise_for_status()
        
        # Parse XML (strip namespaces for easier searching if needed, or use the exact namespace)
        root = ET.fromstring(resp.text)
        namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        for url in root.findall('sm:url', namespace):
            loc = url.find('sm:loc', namespace)
            if loc is not None:
                href = loc.text
                # Filter for India jobs
                if '/jobs/' in href and 'india' in href.lower():
                    # The title is usually embedded in the URL slug: 
                    # https://careers.servicenow.com/jobs/1234/software-engineer-india/
                    parts = href.strip('/').split('/')
                    raw_title = parts[-1] if len(parts) > 0 else "ServiceNow Job"
                    title = raw_title.replace('-', ' ').title()
                    
                    jobs.append({
                        "company": name,
                        "title": title,
                        "location": "India",
                        "type": "N/A",
                        "apply_url": href,
                        "ats": "servicenow"
                    })
            
        logger.info("[ServiceNow] fetched %d jobs via sitemap", len(jobs))
        return jobs
    except Exception as exc:
        logger.error("[ServiceNow] error fetching sitemap: %s", exc)
        return []
