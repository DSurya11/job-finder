import asyncio
import json
import re
import urllib.parse
import httpx
from playwright.async_api import async_playwright

COMPANIES = {
    "Cisco": "https://jobs.cisco.com",
    "DE Shaw": "https://www.deshawindia.com/careers/",
    "Zerodha": "https://careers.zerodha.com",
    "Goldman Sachs": "https://www.goldmansachs.com/careers/",
    "Sprinklr": "https://www.sprinklr.com/careers/",
    "Walmart Global Tech": "https://careers.walmart.com",
    "Uber": "https://jobs.uber.com/en/",
    "Salesforce": "https://www.salesforce.com/company/careers/",
    "Meesho": "https://careers.meesho.com",
    "InMobi": "https://www.inmobi.com/company/careers",
    "Postman": "https://www.postman.com/company/careers/",
    "Groww": "https://groww.in/careers",
    "Ola": "https://olacareers.com",
    "JPMorgan Chase": "https://careers.jpmorgan.com",
    "Morgan Stanley": "https://www.morganstanley.com/people",
    "Deutsche Bank": "https://careers.db.com",
    "Optiver": "https://www.optiver.com/join-us/",
    "Citadel Securities": "https://citadelsecurities.com/careers",
    "Visa": "https://careers.visa.com",
    "Mastercard": "https://mastercard.com/careers",
    "American Express": "https://aexp.eightfold.ai",
    "PayPal": "https://careers.pypl.com/home/"
}

# Slugs to try: standard name, no spaces, dash
def get_slugs(name):
    lower = name.lower()
    return list(set([
        lower.replace(' ', ''),
        lower.replace(' ', '-'),
        lower.split(' ')[0]
    ]))

ATS_APIS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/{slug}/postings",
    "workable": "https://www.workable.com/api/accounts/{slug}?details=false",
    "recruitee": "https://{slug}.recruitee.com/api/offers"
}

SITEMAP_PATHS = ['/sitemap.xml', '/sitemap-jobs.xml', '/sitemap_index.xml', '/sitemap/sitemap.xml']

results = {}

async def probe_ats(client, name):
    slugs = get_slugs(name)
    for ats, url_template in ATS_APIS.items():
        for slug in slugs:
            url = url_template.format(slug=slug)
            try:
                r = await client.get(url, timeout=5)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        # sanity check - workable returns 200 even for non-existent sometimes, lever does too if empty
                        if ats == 'lever' and isinstance(data, list):
                            return ats, slug, url
                        if ats == 'greenhouse' and data.get('jobs') is not None:
                            return ats, slug, url
                        if ats == 'smartrecruiters' and data.get('totalFound', 0) > 0:
                            return ats, slug, url
                        if ats == 'ashby' and data.get('jobs') is not None:
                            return ats, slug, url
                        if ats == 'recruitee' and data.get('offers') is not None:
                            return ats, slug, url
                        if ats == 'workable' and len(data.get('jobs', [])) > 0:
                            return ats, slug, url
                    except:
                        pass
            except Exception:
                pass
    return None, None, None

async def check_sitemap(client, base_url):
    parsed = urllib.parse.urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    for path in SITEMAP_PATHS:
        try:
            r = await client.get(domain + path, timeout=5)
            if r.status_code == 200 and 'xml' in r.text.lower():
                return domain + path
        except:
            pass
    return None

async def stage1(client, name, url):
    print(f"[{name}] Starting Stage 1...")
    ats, slug, ats_url = await probe_ats(client, name)
    if ats:
        print(f"[{name}] FOUND ATS: {ats} ({slug})")
        return {"method_found": f"ats_api_{ats}", "endpoint_or_url": ats_url, "status": "Success", "notes": f"Native JSON API discovered ({ats})"}
    
    print(f"[{name}] Probing sitemap...")
    sitemap = await check_sitemap(client, url)
    if sitemap:
        print(f"[{name}] FOUND SITEMAP: {sitemap}")
        return {"method_found": "sitemap", "endpoint_or_url": sitemap, "status": "Success", "notes": "Sitemap available for scraping"}
        
    return None

async def check_robots(client, url):
    parsed = urllib.parse.urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        r = await client.get(robots_url, timeout=5)
        if r.status_code == 200:
            if 'Disallow: /' in r.text and 'Allow: /' not in r.text:
                return "Restricted"
        return "Allowed"
    except:
        return "Unknown"

async def stage2(name, url):
    print(f"[{name}] Starting Stage 2 Playwright...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0")
            page = await context.new_page()
            
            responses = []
            page.on("response", lambda r: responses.append({"url": r.url, "status": r.status}))
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=20000)
            except Exception as e:
                print(f"[{name}] PW Timeout: {e}")
                
            await browser.close()
            
            # Analyze responses for third-party ATS
            third_party_ats = [
                'eightfold.ai', 'phenompeople', 'myworkdayjobs', 'icims',
                'taleo', 'successfactors', 'mynexthire', 'greenhouse.io', 'lever.co'
            ]
            
            for req in responses:
                for ats in third_party_ats:
                    if ats in req["url"].lower():
                        return {"method_found": "third_party_ats", "endpoint_or_url": req["url"], "status": str(req["status"]), "notes": f"Detected {ats} in network requests"}
                        
            # If nothing found, check if responses were mostly 403
            status_codes = [r["status"] for r in responses]
            if 403 in status_codes and len(status_codes) < 10:
                return {"method_found": "blocked", "endpoint_or_url": url, "status": "403", "notes": "Blocked by WAF during browser load"}
                
            return {"method_found": "dom_scrape_required", "endpoint_or_url": url, "status": "200", "notes": "No ATS or API found. Requires DOM scraping."}
            
    except Exception as e:
        return {"method_found": "error", "endpoint_or_url": url, "status": "Error", "notes": str(e)}

async def main():
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=10) as client:
        for name, url in COMPANIES.items():
            res = await stage1(client, name, url)
            if res:
                results[name] = res
            else:
                res = await stage2(name, url)
                results[name] = res
                
            # robots check
            if res["method_found"] in ["third_party_ats", "dom_scrape_required"]:
                robots = await check_robots(client, res["endpoint_or_url"])
                results[name]["notes"] += f" (Robots.txt: {robots})"
                
    with open("discovery_results.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())
