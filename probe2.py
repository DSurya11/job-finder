import asyncio
from playwright.async_api import async_playwright

async def probe2():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        page = await context.new_page()

        print('\n--- Zerodha Detailed ---')
        try:
            await page.goto('https://careers.zerodha.com', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            text = await page.evaluate('document.body.innerText')
            print('Text snippet:', text[:500].replace('\n', ' '))
            
            jobs = await page.evaluate('''
                Array.from(document.querySelectorAll("li, a, div"))
                .map(e => e.innerText)
                .filter(t => t && (t.includes("Engineer") || t.includes("Developer") || t.includes("Hiring")))
                .slice(0, 5)
            ''')
            print('Matches:', jobs)
        except Exception as e: print(e)

        print('\n--- DE Shaw Detailed ---')
        try:
            await page.goto('https://www.deshawindia.com/careers/job-openings', wait_until='networkidle')
            await page.wait_for_timeout(3000)
            text = await page.evaluate('document.body.innerText')
            print('Text snippet:', text[:500].replace('\n', ' '))
        except Exception as e: print(e)

        await browser.close()

asyncio.run(probe2())
