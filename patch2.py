import json
import sys
sys.path.append('c:/job-finder')
from generate_dashboard import generate_dashboard

with open('c:/job-finder/output/jobs.json', encoding='utf-8') as f:
    jobs = json.load(f)

for j in jobs:
    if j.get('company') == 'Goldman Sachs' and 'apply_url' in j:
        if '_GS_MID_CAREER' in j['apply_url']:
            j['apply_url'] = j['apply_url'].replace('_GS_MID_CAREER', '')
        elif '_GS_EARLY_CAREER' in j['apply_url']:
            j['apply_url'] = j['apply_url'].replace('_GS_EARLY_CAREER', '')

with open('c:/job-finder/output/jobs.json', 'w', encoding='utf-8') as f:
    json.dump(jobs, f, indent=2)

generate_dashboard(jobs, 'c:/job-finder/output/dashboard.html')
print("Dashboard updated with GS URLs!")
