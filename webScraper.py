import asyncio
from playwright.async_api import async_playwright

URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"


async def auto_scroll(page):
    prev_height = 0

    while True:
        curr_height = await page.evaluate("document.body.scrollHeight")

        if curr_height == prev_height:
            break

        prev_height = curr_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)


async def load_full_innings(page):
    prev_count = 0

    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.2)

        balls = page.locator("div.border-b.pb-2")
        count = await balls.count()

        print(f"Loaded balls: {count}")

        if count == prev_count:
            print("✅ Innings fully loaded")
            break

        prev_count = count


async def wait_for_innings_change(page, old_html):
    print("👀 Waiting for innings change (DOM watcher)...")

    await page.wait_for_function(
   """(old) => {
        const el = document.querySelector('div.border-b.pb-2')?.parentElement;
        return el && el.innerHTML !== old;
    }""" ,
    arg=old_html,
    timeout=60000
)

    print("🔄 Innings change detected!")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        # page.on("response", lambda r: print("🌐", r.status, r.url))

        print("Opening page...")
        await page.goto(URL)
        await page.wait_for_load_state("networkidle")

        print("Clicking Ball by Ball tab...")
        await page.click("text=Ball by Ball")

        await page.wait_for_selector("div.border-b.pb-2")

        # =========================
        # INNINGS 1
        # =========================
        print("\n👉 Load first innings (manually select if needed)...")

        await load_full_innings(page)

        # capture container HTML signature
        container = page.locator("div.border-b.pb-2").first.locator("..")
        old_html = await container.inner_html()

        html1 = await page.content()
        with open("innings_1.html", "w", encoding="utf-8") as f:
            f.write(html1)

        print("✅ Saved innings_1.html")

        # =========================
        # WAIT FOR INNINGS CHANGE
        # =========================
        print("\n👉 Now switch innings in UI (script will detect automatically)")

        await wait_for_innings_change(page, old_html)

        # =========================
        # INNINGS 2
        # =========================
        print("Loading second innings...")

        await load_full_innings(page)

        html2 = await page.content()
        with open("innings_2.html", "w", encoding="utf-8") as f:
            f.write(html2)

        print("✅ Saved innings_2.html")

        await browser.close()


asyncio.run(main())
