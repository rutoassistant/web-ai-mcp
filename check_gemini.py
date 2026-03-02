import asyncio
from patchright.async_api import async_playwright

async def run():
    p = await async_playwright().start()
    b = await p.chromium.launch(headless=False, args=['--disable-blink-features=AutomationControlled'])
    c = await b.new_context(viewport={'width': 1280, 'height': 720}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    page = await c.new_page()
    await page.goto('https://gemini.google.com/app', wait_until='domcontentloaded')
    await page.wait_for_timeout(5000)
    await page.screenshot(path='/app/data/gemini_direct.png')
    await b.close()

asyncio.run(run())