import asyncio
from playwright.async_api import async_playwright


# ---------------- AUTO LOAD ALL BALLS ----------------

async def load_full_innings(page):
    prev_count = 0

    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.2)

        balls = page.locator("div.border-b.pb-2")
        count = await balls.count()

        print(f"📊 Loaded balls: {count}")

        if count == prev_count:
            print("✅ Innings fully loaded")
            break

        prev_count = count


# ---------------- WAIT FOR INNINGS SWITCH ----------------

async def wait_for_innings_change(page, old_html):
    print("👀 Waiting for innings change (switch in UI)...")

    await page.wait_for_function(
        """(old) => {
            const el = document.querySelector('div.border-b.pb-2')?.parentElement;
            return el && el.innerHTML !== old;
        }""",
        arg=old_html,
        timeout=60000
    )

    print("🔄 Innings change detected!")


# ---------------- MAIN SCRAPER ----------------

async def scrape_match(url, headless=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        print("🌐 Opening page...")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        print("🖱 Clicking Ball by Ball tab...")
        await page.click("text=Ball by Ball")

        await page.wait_for_selector("div.border-b.pb-2")

        # =========================
        # INNINGS 1
        # =========================
        print("\n👉 Loading first innings...")

        await load_full_innings(page)

        # Capture container HTML signature
        container = page.locator("div.border-b.pb-2").first.locator("..")
        old_html = await container.inner_html()

        html1 = await page.content()
        file1 = "innings_1.html"

        with open(file1, "w", encoding="utf-8") as f:
            f.write(html1)

        print(f"✅ Saved {file1}")

        # =========================
        # WAIT FOR USER TO SWITCH INNINGS
        # =========================
        print("\n👉 Please switch innings in UI (script will auto-detect)")

        await wait_for_innings_change(page, old_html)

        # =========================
        # INNINGS 2
        # =========================
        print("\n👉 Loading second innings...")

        await load_full_innings(page)

        html2 = await page.content()
        file2 = "innings_2.html"

        with open(file2, "w", encoding="utf-8") as f:
            f.write(html2)

        print(f"✅ Saved {file2}")

        await browser.close()

        # 🔥 RETURN FILES (IMPORTANT)
        return [file1, file2]


# ---------------- OPTIONAL RUN (for testing scraper alone) ----------------

if __name__ == "__main__":
    URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"

    async def run():
        files = await scrape_match(URL)
        print("📁 Files returned:", files)

    asyncio.run(run())