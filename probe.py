import asyncio
from playwright.async_api import async_playwright

async def probe():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        page = await context.new_page()

        print('\n--- DE Shaw ---')
        try:
            await page.goto('https://www.deshawindia.com/careers/')
            await page.wait_for_timeout(3000)
            print(await page.title())
            html = await page.content()
            import re
            jobs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html)
            for j in jobs:
                if 'careers' in j[0]: print(j)
        except Exception as e: print("Err:", e)

        print('\n--- Zerodha ---')
        try:
            await page.goto('https://careers.zerodha.com')
            await page.wait_for_timeout(3000)
            print(await page.title())
            html = await page.content()
            jobs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html)
            for j in jobs:
                print(j)
        except Exception as e: print("Err:", e)

        print('\n--- Salesforce ---')
        try:
            await page.goto('https://careers.salesforce.com/en/jobs/?search=&country=India&pagesize=20#results')
            await page.wait_for_timeout(5000)
            print(await page.title())
            html = await page.content()
            jobs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', html)
            for j in jobs:
                if 'job' in j[0].lower(): print(j)
        except Exception as e: print("Err:", e)
            
        await browser.close()

asyncio.run(probe())
