import csv
import json
import time
import requests
from bs4 import BeautifulSoup

COMPANIES = [
    ("DE Shaw", "https://www.deshawindia.com/careers/"),
    ("Zerodha", "https://zerodha.com/careers"),
    ("Goldman Sachs", "https://www.goldmansachs.com/careers/"),
    ("Sprinklr", "https://www.sprinklr.com/careers/"),
    ("Walmart Global Tech", "https://careers.walmart.com/"),
    ("Uber", "https://uber.com/careers"),
    ("Salesforce", "https://salesforce.com/company/careers"),
    ("ServiceNow", "https://careers.servicenow.com"),
    ("Cisco", "https://jobs.cisco.com"),
    ("Swiggy", "https://careers.swiggy.com"),
    ("Zomato", "https://careers.zomato.com"),
    ("PhonePe", "https://phonepe.com/careers"),
    ("Meesho", "https://careers.meesho.com"),
    ("Freshworks", "https://freshworks.com/company/careers"),
    ("InMobi", "https://inmobi.com/company/careers"),
    ("Postman", "https://postman.com/company/careers"),
    ("Groww", "https://groww.in/careers"),
    ("Ola", "https://olacareers.com"),
    ("JPMorgan Chase", "https://careers.jpmorgan.com"),
    ("Morgan Stanley", "https://morganstanley.com/careers"),
    ("Deutsche Bank", "https://careers.db.com"),
    ("Optiver", "https://optiver.com/working-at-optiver"),
    ("Citadel Securities", "https://citadelsecurities.com/careers"),
    ("SAP Labs India", "https://jobs.sap.com"),
    ("Visa", "https://careers.visa.com"),
    ("Mastercard", "https://mastercard.com/careers"),
    ("American Express", "https://aexp.eightfold.ai"),
    ("PayPal", "https://paypal.com/us/webapps/mpp/jobs")
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
}

def check_schema_in_json(data):
    """Recursively search JSON for @type: JobPosting"""
    count = 0
    if isinstance(data, dict):
        if data.get("@type") == "JobPosting":
            count += 1
        elif data.get("@type") == "DataFeed":
            # Sometimes datafeeds contain multiple JobPostings
            pass
            
        for v in data.values():
            count += check_schema_in_json(v)
    elif isinstance(data, list):
        for item in data:
            count += check_schema_in_json(item)
    return count

def check_url(url):
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            status = resp.status_code
            
            if status == 403:
                return status, False, 0, "blocked/403 (bot protection)"
            
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            job_postings_found = 0
            
            # Check for JSON-LD scripts
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if script.string:
                    try:
                        data = json.loads(script.string)
                        job_postings_found += check_schema_in_json(data)
                    except json.JSONDecodeError:
                        continue
            
            notes = []
            if job_postings_found == 0:
                # Heuristic: Is it a JS-rendered page?
                if len(soup.find_all('a')) < 5:
                    notes.append("likely JS-rendered - very few links in raw HTML")
                elif "job" not in resp.text.lower():
                    notes.append("static marketing page not job list")
                else:
                    notes.append("no JobPosting schema found")
            else:
                notes.append("schema found!")
                
            if len(resp.history) > 0:
                notes.append(f"redirected to {resp.url}")
                
            return status, job_postings_found > 0, job_postings_found, " | ".join(notes)
            
        except requests.RequestException as e:
            if attempt == 0:
                time.sleep(2)
                continue
            return None, False, 0, f"Request failed: {type(e).__name__}"
            
    return None, False, 0, "Failed after 2 attempts"

def main():
    results = []
    success_count = 0
    blocked_js_count = 0
    
    print(f"{'Company':<25} | {'Status':<6} | {'Schema':<6} | {'Count':<5} | {'Notes'}")
    print("-" * 100)
    
    for name, url in COMPANIES:
        status, has_schema, count, notes = check_url(url)
        
        print(f"{name:<25} | {str(status):<6} | {str(has_schema):<6} | {count:<5} | {notes}")
        
        results.append({
            "company_name": name,
            "url": url,
            "has_jobposting_schema": has_schema,
            "num_jobpostings_found": count,
            "http_status": status,
            "notes": notes
        })
        
        if has_schema:
            success_count += 1
        else:
            blocked_js_count += 1
            
        time.sleep(2)
        
    with open('schema_check_results.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["company_name", "url", "has_jobposting_schema", "num_jobpostings_found", "http_status", "notes"])
        writer.writeheader()
        writer.writerows(results)
        
    print("-" * 100)
    print(f"\n{success_count} of 28 companies expose JobPosting schema and can likely be scraped without Apify.")
    print(f"{blocked_js_count} companies are blocked or JS-rendered and still need manual/Apify handling.")
    print("\nResults saved to schema_check_results.csv")

if __name__ == "__main__":
    main()
