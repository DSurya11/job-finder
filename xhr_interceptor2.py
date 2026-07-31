import asyncio
import json
import base64
from playwright.async_api import async_playwright

COMPANIES = {
    "Cisco": "https://jobs.cisco.com/jobs/SearchJobs/?21178=%5B169482%5D&21178_format=6020&listFilterMode=1",
    "ServiceNow": "https://careers.servicenow.com/careers/jobs?location=India&categories=Engineering",
    "SAP Labs India": "https://jobs.sap.com/search/?q=software&locationsearch=India",
    "Swiggy": "https://careers.swiggy.com/search/?q=software",
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
                        # check if it's application/json
                        ct = response.headers.get("content-type", "")
                        if "application/json" in ct.lower():
                            url_str = response.url
                            if any(tracker in url_str.lower() for tracker in ["analytics", "track", "pixel", "telemetry", "google-analytics", "metrics", "log"]):
                                return
                                
                            try:
                                body = await response.json()
                                if isinstance(body, dict) or isinstance(body, list):
                                    req_headers = response.request.headers
                                    # store minimal data to avoid huge logs
                                    post_data = response.request.post_data
                                    requests_caught.append({
                                        "url": url_str,
                                        "method": response.request.method,
                                        "status": response.status,
                                        "post_data": post_data,
                                        "sample_response_keys": list(body.keys()) if isinstance(body, dict) else "List"
                                    })
                            except Exception:
                                pass
                except Exception:
                    pass

            page.on("response", handle_response)
            
            try:
                print(f"Navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(5000)
                
                # Scroll a bit
                await page.evaluate("window.scrollBy(0, 500)")
                await page.wait_for_timeout(2000)
                
                # Look for a search input and type something if possible
                search_inputs = await page.locator("input[type='search'], input[type='text']").all()
                if search_inputs:
                    try:
                        await search_inputs[0].fill("Software Engineer")
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(3000)
                    except:
                        pass
                
            except Exception as e:
                print(f"Navigation error: {e}")
                
            # Filter and print
            valid_reqs = []
            for req in requests_caught:
                # ignore small config responses
                if req['sample_response_keys'] == "List" or len(req['sample_response_keys']) > 2:
                    valid_reqs.append(req)
                    
            if valid_reqs:
                print(f"Found {len(valid_reqs)} potential JSON APIs!")
                for idx, req in enumerate(valid_reqs):
                    print(f"  [{idx+1}] {req['method']} {req['url']}")
            else:
                print("No JSON APIs detected.")
                
            results[name] = valid_reqs
            await page.close()
            
        with open("xhr_results.json", "w") as f:
            json.dump(results, f, indent=2)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
