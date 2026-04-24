import asyncio
from playwright.async_api import async_playwright

URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"

async def auto_scroll(page):
    previous_height = 0

    while True:
        current_height = await page.evaluate("document.body.scrollHeight")

        if current_height == previous_height:
            break

        previous_height = current_height

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)  # wait for lazy load


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # keep False for debugging
        context = await browser.new_context()
        page = await context.new_page()

        print("Opening page...")
        await page.goto(URL, timeout=60000)

        # Wait for page to stabilize
        await page.wait_for_load_state("networkidle")

        print("Clicking Ball by Ball tab...")
        # Adjust selector if needed
        await page.click("text=Ball by Ball")

        # Wait for content to load
        await page.wait_for_timeout(3000)

        print("Scrolling to load all data...")
        await auto_scroll(page)

        # Extra wait to ensure rendering complete
        await page.wait_for_timeout(2000)

        print("Capturing full HTML...")
        html_content = await page.content()

        # Save file
        with open("ball_by_ball_full.html", "w", encoding="utf-8") as f:
            f.write(html_content)

        print("✅ HTML saved as ball_by_ball_full.html")

        await browser.close()


asyncio.run(main())