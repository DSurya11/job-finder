import asyncio
import json
from urllib.parse import urlparse
from playwright.async_api import async_playwright

COMPANIES = {
    "Cisco": "https://jobs.cisco.com/jobs/SearchJobs/?21178=%5B169482%5D&21178_format=6020&listFilterMode=1",
    "ServiceNow": "https://careers.servicenow.com/careers/jobs?location=India&categories=Engineering",
    "SAP Labs India": "https://jobs.sap.com/search/?q=software&locationsearch=India",
    "Swiggy": "https://careers.swiggy.com/search/?q=software",
    "PhonePe": "https://phonepe.com/careers",
    "Freshworks": "https://freshworks.com/company/careers"
}

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        results = {}
        
        for name, url in COMPANIES.items():
            print(f"\\n--- Investigating {name} ---")
            page = await context.new_page()
            
            requests_caught = []
            
            async def handle_response(response):
                try:
                    if response.request.resource_type in ["fetch", "xhr"]:
                        url_str = response.url
                        if any(keyword in url_str.lower() for keyword in ["job", "search", "graphql", "api"]):
                            # ignore tracking/analytics
                            if any(tracker in url_str.lower() for tracker in ["analytics", "track", "pixel", "telemetry"]):
                                return
                                
                            try:
                                body = await response.json()
                                # Check if it looks like a job listing payload
                                if isinstance(body, dict) or isinstance(body, list):
                                    req_headers = response.request.headers
                                    requests_caught.append({
                                        "url": url_str,
                                        "method": response.request.method,
                                        "status": response.status,
                                        "headers": req_headers,
                                        "post_data": response.request.post_data,
                                        "sample_response_keys": list(body.keys()) if isinstance(body, dict) else "List"
                                    })
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", handle_response)
            
            try:
                print(f"Navigating to {url}")
                await page.goto(url, wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"Navigation error: {e}")
                
            if requests_caught:
                print(f"Found {len(requests_caught)} potential JSON APIs!")
                for idx, req in enumerate(requests_caught):
                    print(f"  [{idx+1}] {req['method']} {req['url']}")
            else:
                print("No JSON APIs detected.")
                
            results[name] = requests_caught
            await page.close()
            
        with open("xhr_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
