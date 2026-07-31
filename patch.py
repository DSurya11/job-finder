import json
from generate_dashboard import generate_dashboard

with open('c:/job-finder/output/jobs.json', encoding='utf-8') as f:
    jobs = json.load(f)

for j in jobs:
    if 'apply_url' not in j and 'url' in j:
        j['apply_url'] = j.pop('url')
    if 'ats_source' not in j:
        if j['company'] == 'Goldman Sachs':
            j['ats_source'] = 'GS GraphQL'
        elif j['company'] == 'JPMorgan Chase':
            j['ats_source'] = 'Oracle Cloud HCM'
    if 'date_fetched' not in j:
        j['date_fetched'] = '2026-07-14'

with open('c:/job-finder/output/jobs.json', 'w', encoding='utf-8') as f:
    json.dump(jobs, f, indent=2)

generate_dashboard(jobs, 'c:/job-finder/output/dashboard.html')
print("Dashboard updated successfully!")
