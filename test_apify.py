import asyncio
import os
import json
from apify_client import ApifyClientAsync
from dotenv import load_dotenv

load_dotenv()
APIFY_TOKEN = os.getenv('APIFY_API_TOKEN')

async def fetch_test():
    client = ApifyClientAsync(APIFY_TOKEN)
    print('Calling Microsoft...')
    run = await client.actor('apify/puppeteer-scraper').call(run_input={
        'startUrls': [{'url': 'https://jobs.careers.microsoft.com/global/en/search?l=en_us&pg=1&pgSz=20&loc=India'}],
        'pageFunction': '''async ({ page, request }) => {
    await page.waitForSelector('a[aria-label^=\"View job:\"]', { timeout: 10000 }).catch(() => {});
    return await page.evaluate(() => {
        const jobs = [];
        document.querySelectorAll('a[aria-label^=\"View job:\"]').forEach(el => {
            let title = el.getAttribute('aria-label') || '';
            title = title.replace('View job:', '').trim();
            const text = el.innerText || '';
            const lines = text.split('\\n').map(l => l.trim()).filter(l => l);
            const location = lines.length > 1 ? lines[1] : '';
            if (title) jobs.push({ title, location });
        });
        return jobs;
    });
}''',
        'proxyConfiguration': {'useApifyProxy': True},
        'waitUntil': ['networkidle2']
    })
    
    print('Results:')
    async for item in client.dataset(run.default_dataset_id).iterate_items():
        if isinstance(item, list):
            for i in item: print(json.dumps(i))
        else:
            print(json.dumps(item))

if __name__ == '__main__':
    asyncio.run(fetch_test())
