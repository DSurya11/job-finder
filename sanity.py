import requests
import xml.etree.ElementTree as ET
import socket
import re

print('\n=== 1. ATS API Sanity Check ===')
apis = {
    'Meesho (Lever)': 'https://api.lever.co/v0/postings/meesho?mode=json',
    'InMobi (Greenhouse)': 'https://boards-api.greenhouse.io/v1/boards/inmobi/jobs',
    'Postman (Greenhouse)': 'https://boards-api.greenhouse.io/v1/boards/postman/jobs',
    'Groww (Greenhouse)': 'https://boards-api.greenhouse.io/v1/boards/groww/jobs',
    'Optiver (Greenhouse)': 'https://boards-api.greenhouse.io/v1/boards/optiver/jobs',
    'Uber (SmartRecruiters)': 'https://api.smartrecruiters.com/v1/companies/uber/postings',
    'Visa (SmartRecruiters)': 'https://api.smartrecruiters.com/v1/companies/visa/postings'
}
for name, url in apis.items():
    try:
        r = requests.get(url, timeout=10).json()
        if 'greenhouse' in url:
            jobs = r.get('jobs', [])
            titles = [j.get('title', '') for j in jobs[:2]]
        elif 'lever' in url:
            jobs = r
            titles = [j.get('text', '') for j in jobs[:2]]
        elif 'smartrecruiters' in url:
            jobs = r.get('content', [])
            titles = [j.get('name', '') for j in jobs[:2]]
        
        print(f'{name}: {len(jobs)} jobs. Samples: {titles}')
    except Exception as e:
        print(f'{name}: Error {e}')

print('\n=== 2. Sitemap Sanity Check ===')
sitemaps = {
    'Goldman Sachs': 'https://www.goldmansachs.com/sitemap.xml',
    'Sprinklr': 'https://www.sprinklr.com/sitemap.xml',
    'Walmart Global Tech': 'https://careers.walmart.com/sitemap.xml',
    'JPMorgan Chase': 'https://careers.jpmorgan.com/sitemap.xml',
    'Morgan Stanley': 'https://www.morganstanley.com/sitemap.xml'
}
for name, url in sitemaps.items():
    try:
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
        text = re.sub(r'\sxmlns="[^"]+"', '', r.text, count=1)
        root = ET.fromstring(text)
        urls = [u.text for u in root.findall('.//url/loc')]
        if not urls:
            urls = [u.text for u in root.findall('.//sitemap/loc')]
        print(f'{name}: {len(urls)} URLs. Samples: {urls[:2]}')
    except Exception as e:
        print(f'{name}: Error {e}')

print('\n=== 3. Ola Domain Check ===')
for d in ['olacareers.com', 'olacabs.com', 'ola.com', 'careers.olaelectric.com', 'careers.olacabs.com']:
    try:
        ip = socket.gethostbyname(d)
        print(f'{d}: Resolves to {ip}')
    except:
        print(f'{d}: NXDOMAIN')

print('\n=== 4. American Express Eightfold Check ===')
try:
    r = requests.get('https://aexp.eightfold.ai/api/apply/v2/jobs?domain=aexp.com&start=0&num=10', headers={'User-Agent':'Mozilla/5.0'}, timeout=10)
    print('Eightfold status GET:', r.status_code)
    try:
        data = r.json()
        jobs = data.get('positions', [])
        print(f'Eightfold: {len(jobs)} jobs. Samples: {[j.get("name") for j in jobs[:2]]}')
    except:
        print('Not json:', r.text[:200])
except Exception as e:
    print('Eightfold Error', e)
