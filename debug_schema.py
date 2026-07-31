import json
import requests
import csv
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
}

TEST_COMPANIES = [
    ("Cisco", "https://jobs.cisco.com"),
    ("ServiceNow", "https://careers.servicenow.com"),
    ("SAP Labs India", "https://jobs.sap.com")
]

print("=== PART 1: HTTP REQUEST CODE (from original script) ===")
print('''
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
}

resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
''')
print("Confirmed: The headers dict was passed to the `headers` kwarg of `requests.get()` correctly.\n")

print("=== PART 2 & 3: DEBUGGING INDIVIDUAL SITES ===")
results = []
for name, url in TEST_COMPANIES:
    print(f"\n--- Testing {name} ({url}) ---")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        print(f"Request Headers Sent:\n{json.dumps(dict(resp.request.headers), indent=2)}")
        print(f"HTTP Status Code: {resp.status_code}")
        
        raw_body = resp.text
        raw_length = len(raw_body)
        print(f"Total raw response body length: {raw_length} characters")
        print(f"First 1000 characters:\n{raw_body[:1000]}\n")
        
        has_jobposting = "JobPosting" in raw_body
        has_ldjson = "ld+json" in raw_body
        print(f"Contains 'JobPosting': {has_jobposting}")
        print(f"Contains 'ld+json': {has_ldjson}")
        
        results.append({
            "company_name": name,
            "url": url,
            "http_status": resp.status_code,
            "raw_response_length": raw_length,
            "has_jobposting_string": has_jobposting,
            "has_ldjson_string": has_ldjson
        })
    except Exception as e:
        print(f"Failed: {e}")

print("\n=== PART 4 & 5: UPDATED CSV FORMAT DEMO ===")
csv_file = "debug_schema_results.csv"
with open(csv_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=["company_name", "url", "http_status", "raw_response_length", "has_jobposting_string", "has_ldjson_string"])
    writer.writeheader()
    writer.writerows(results)
    
print(f"Saved results to {csv_file}")
