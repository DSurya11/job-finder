import asyncio
from playwright.async_api import async_playwright

async def probe3():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        page = await context.new_page()

        print('\n--- Zerodha Buttons ---')
        try:
            await page.goto('https://careers.zerodha.com', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            buttons = await page.evaluate('''
                Array.from(document.querySelectorAll("a, button")).map(e => e.innerText + ' -> ' + e.href)
            ''')
            for b in buttons:
                if 'apply' in b.lower() or 'job' in b.lower() or 'open' in b.lower() or 'career' in b.lower(): print(b)
        except Exception as e: print(e)

        print('\n--- DE Shaw Iframes / Buttons ---')
        try:
            await page.goto('https://www.deshawindia.com/careers/job-openings', wait_until='networkidle')
            await page.wait_for_timeout(2000)
            iframes = await page.evaluate('Array.from(document.querySelectorAll("iframe")).map(i => i.src)')
            print('Iframes:', iframes)
            buttons = await page.evaluate('''
                Array.from(document.querySelectorAll("a, button")).map(e => e.innerText + ' -> ' + e.href)
            ''')
            for b in buttons:
                if 'apply' in b.lower() or 'job' in b.lower() or 'search' in b.lower() or 'open' in b.lower() or 'career' in b.lower(): print(b)
        except Exception as e: print(e)

        await browser.close()

asyncio.run(probe3())
