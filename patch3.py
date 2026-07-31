import json
import yaml
import sys
sys.path.append('c:/job-finder')
from generate_dashboard import generate_dashboard

with open('c:/job-finder/companies.yaml', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    companies = config['companies']

# From main.py logic:
# All companies with "ats": "custom" AND any company that doesn't have an "ats" field
custom_ats_companies = []
custom_handled = {'dom_scraper', 'amazon', 'gs_graphql', 'oracle', 'swiggy', 'sitemap', 'servicenow', 'sap'}
for c in companies:
    ats = c.get('ats', 'custom')
    if ats == 'custom' or ats not in ('greenhouse', 'lever', 'ashby', 'workday') and ats not in custom_handled:
        # Exclude those that are fully implemented but labeled custom in my script somehow
        if c['name'] not in ['Salesforce']: 
            custom_ats_companies.append({
                "name": c['name'],
                "careers_url": c.get('careers_url', '#')
            })

# Ensure Salesforce and Zomato, Morgan Stanley, etc.
# Actually, the user wants to see Cisco, Uber, PayPal, Morgan Stanley, Zomato
custom_ats_companies = [
    {"name": c['name'], "careers_url": c.get('careers_url', '#')}
    for c in companies if c.get('ats') == 'custom' or ('ats' not in c)
]

with open('c:/job-finder/output/jobs.json', encoding='utf-8') as f:
    jobs = json.load(f)

# Load metadata
try:
    with open('c:/job-finder/output/history.json', encoding='utf-8') as f:
        history = json.load(f)
except:
    history = {}
    
company_metadata = {}
for c_name, data in history.items():
    company_metadata[c_name] = {
        "current_count": data.get("count", 0),
        "previous_count": data.get("count", 0),
        "last_success": data.get("last_success", "Never"),
        "anomaly": False,
        "anomaly_reason": ""
    }

generate_dashboard(jobs, 'c:/job-finder/output/dashboard.html', custom_ats_companies, company_metadata)
print("Dashboard updated with Not Yet Integrated list!")
