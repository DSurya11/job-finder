import yaml
with open('c:/job-finder/companies.yaml', encoding='utf-8') as f:
    config = yaml.safe_load(f)

seen = set()
cleaned = []
for c in config['companies']:
    if c['name'] not in seen:
        seen.add(c['name'])
        cleaned.append(c)

config['companies'] = cleaned
with open('c:/job-finder/companies.yaml', 'w', encoding='utf-8') as f:
    yaml.safe_dump(config, f, sort_keys=False)
print("Deduplicated companies.yaml")
