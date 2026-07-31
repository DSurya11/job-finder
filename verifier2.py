import asyncio
import requests
import logging

logging.basicConfig(level=logging.ERROR)

async def check_ola():
    print('\n--- 1. Ola Check ---')
    url = 'https://careers.olacabs.com'
    try:
        r = requests.get(url, timeout=30)
        print(f'Success: {r.status_code}')
        print(r.text[:200])
    except Exception as e:
        print(f'Failed: {type(e).__name__} - {e}')

async def check_deshaw():
    print('\n--- 2. DE Shaw Check ---')
    from playwright.async_api import async_playwright
    from fetchers.extractors.deshaw import extract_jobs
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            jobs = await extract_jobs(page, 'https://www.deshawindia.com/careers/job-openings', 'DE Shaw')
            titles = [j['title'] for j in jobs]
            unique_titles = set(titles)
            print(f'len(jobs): {len(jobs)}')
            print(f'len(set(titles)): {len(unique_titles)}')
            print('First 10 titles:')
            for i, t in enumerate(list(unique_titles)[:10]):
                print(f'  {i+1}. {t}')
            await browser.close()
    except Exception as e:
        print('DE Shaw err:', e)

async def check_apify():
    print('\n--- 3. Apify Check (Mastercard, Cisco, PayPal) ---')
    from fetchers.fetch_apify import fetch_apify
    
    async def fetch_and_print(name, url):
        try:
            jobs = await fetch_apify(name, url)
            print(f'\n{name} - Total: {len(jobs)}')
            for i, j in enumerate(jobs[:3]):
                print(f'  {i+1}. Title: {j.get("title")} | Location: {j.get("location", "N/A")}')
        except Exception as e:
            print(f'{name} err: {e}')
            
    await fetch_and_print('Mastercard', 'https://www.mastercard.com/careers')
    await fetch_and_print('Cisco', 'https://jobs.cisco.com')
    await fetch_and_print('PayPal', 'https://careers.pypl.com/home/')

async def main():
    await check_ola()
    await check_deshaw()
    await check_apify()

if __name__ == '__main__':
    asyncio.run(main())
