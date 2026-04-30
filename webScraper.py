import asyncio
import re
from playwright.async_api import async_playwright


# ---------------- UTIL ----------------

def clean_filename(text):
    text = text.replace(" ", "_")
    return re.sub(r'[^a-zA-Z0-9_]', '', text)


async def get_match_title(page):
    for sel in ["h1", "h2", ".match-title", ".title"]:
        loc = page.locator(sel)
        if await loc.count() > 0:
            text = (await loc.first.inner_text()).strip()
            if len(text) > 5:
                print(f"🏏 Match title detected: {text}")
                return text
    return "match"


# ---------------- LOAD BALLS ----------------

async def load_full_innings(page):
    prev_count = 0
    stable_rounds = 0

    for _ in range(20):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)

        count = await page.locator("div.border-b.pb-2").count()
        print(f"📊 Loaded balls: {count}")

        if count == prev_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        if stable_rounds >= 3:
            print("✅ Innings fully loaded")
            return

        prev_count = count

    print("⚠️ Scroll stopped (max loops reached)")


# ---------------- BALL TAB ----------------

async def ensure_ball_by_ball(page, url):
    print("🖱 Ensuring Ball-by-Ball view...")

    # CASE 1: Already loaded
    if await page.locator("div.border-b.pb-2").count() > 0:
        print("✅ Already in Ball-by-ball view")
        return True

    # CASE 2: Try clicking tab
    tab = page.get_by_role("tab", name="Ball by Ball")

    if await tab.count() > 0:
        try:
            await tab.first.click()
            await page.wait_for_timeout(3000)

            if await page.locator("div.border-b.pb-2").count() > 0:
                print("✅ Clicked Ball-by-Ball tab")
                return True
        except:
            pass

    # CASE 3: Force via URL (MOST RELIABLE)
    print("🔄 Reloading with ball_by_ball tab param...")

    if "tab=ball_by_ball" not in url:
        url = url.split("?")[0] + "?tab=ball_by_ball"

    await page.goto(url, wait_until="domcontentloaded")
    await page.wait_for_timeout(4000)

    if await page.locator("div.border-b.pb-2").count() > 0:
        print("✅ Ball-by-ball loaded via URL")
        return True

    print("❌ Could not load Ball-by-ball")
    return False


# ---------------- DROPDOWN ----------------

async def get_innings_dropdown(page):
    balls = page.locator("div.border-b.pb-2")

    if await balls.count() == 0:
        print("⚠️ No ball container")
        return None

    # climb DOM carefully (more stable than fixed index)
    container = balls.first

    for _ in range(5):
        container = container.locator("xpath=..")
        dropdown = container.locator(".ant-dropdown-trigger")

        if await dropdown.count() > 0:
            print("✅ Found innings dropdown (anchored)")
            return dropdown.first

    print("⚠️ Dropdown not found near balls")
    return None


# ---------------- GET INNINGS ----------------

async def get_innings_options(page):
    print("\n👉 Detecting innings options...")

    dropdown = await get_innings_dropdown(page)
    if not dropdown:
        return []

    await dropdown.click()
    await page.wait_for_selector(".ant-dropdown-menu")

    items = page.locator(".ant-dropdown-menu-item")

    options = []
    for i in range(await items.count()):
        text = (await items.nth(i).inner_text()).strip()
        text_lower = text.lower()

        # ✅ STRICT filter: avoid stats menus
        if any(x in text_lower for x in ["wickets", "fours", "sixes", "all"]):
            continue

        # ✅ accept real innings
        if (
            "innings" in text_lower
            or " vs " in text_lower
            or len(text.split()) >= 2
        ):
            options.append(text)

    await page.keyboard.press("Escape")

    print("📋 Innings found:", options)
    return options


# ---------------- CURRENT INNINGS ----------------

async def get_current_innings(page):
    dropdown = await get_innings_dropdown(page)
    if not dropdown:
        return None

    text = (await dropdown.inner_text()).strip()
    print(f"📍 Current innings: {text}")
    return text


# ---------------- SWITCH ----------------

async def switch_to_innings(page, innings_name):
    print(f"\n👉 Switching to: {innings_name}")

    dropdown = await get_innings_dropdown(page)
    if not dropdown:
        print("⚠️ No dropdown → cannot switch")
        return

    old_count = await page.locator("div.border-b.pb-2").count()

    await dropdown.click()
    await page.wait_for_selector(".ant-dropdown-menu")

    await page.locator(".ant-dropdown-menu-item", has_text=innings_name).click()

    await page.wait_for_timeout(1500)

    try:
        await page.wait_for_function(
            """(oldCount) => {
                const newCount = document.querySelectorAll('div.border-b.pb-2').length;
                return newCount !== oldCount;
            }""",
            arg=old_count,
            timeout=15000
        )
    except:
        print("⚠️ Switch timeout (maybe empty innings)")

    print(f"✅ Switched to {innings_name}")


# ---------------- MAIN ----------------

async def scrape_match(url, headless=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        try:
            print("🌐 Opening page...")
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            match_title = await get_match_title(page)
            safe_title = clean_filename(match_title)

            # ✅ ENSURE BALL VIEW
            ok = await ensure_ball_by_ball(page, url)
            if not ok:
                return []

            balls = page.locator("div.border-b.pb-2")

            if await balls.count() == 0:
                print("⚠️ No ball data → skipping")
                return []

            print(f"✅ Balls detected: {await balls.count()}")

            # ---------------- INNINGS ----------------
            innings_list = await get_innings_options(page)

            if not innings_list:
                print("⚠️ No innings → saving single view")

                html = await page.content()
                filename = f"{safe_title}.html"

                with open(filename, "w", encoding="utf-8") as f:
                    f.write(html)

                return [filename]

            current = await get_current_innings(page)

            if current and current in innings_list:
                innings_list.remove(current)
                innings_list.insert(0, current)

            print("✅ Ordered innings:", innings_list)

            files = []

            for i, innings_name in enumerate(innings_list):
                print("\n=========================")
                print(f"👉 Processing innings {i+1}: {innings_name}")

                if i != 0:
                    await switch_to_innings(page, innings_name)

                await load_full_innings(page)

                safe_innings = clean_filename(innings_name)
                filename = f"{safe_title}__{safe_innings}.html"

                html = await page.content()

                with open(filename, "w", encoding="utf-8") as f:
                    f.write(html)

                print(f"✅ Saved {filename}")
                files.append(filename)

            return files

        except Exception as e:
            print(f"❌ ERROR: {e}")
            return []

        finally:
            await browser.close()


# ---------------- RUN ----------------

if __name__ == "__main__":
    # URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"
    # URL = "https://cricclubs.com/LionsSchools/results/APld0Fi3YDjdc8Z23dVqrw?tab=ball_by_ball"
    # URL = "https://cricclubs.com/LionsSchools/results/8bbdBL0iZKW3XhUx9V4H7w?tab=ball_by_ball"
    # URL = "https://cricclubs.com/LionsSchools/results/t3o8pqyPNPRdMvMg7QSfBg?tab=ball_by_ball"
    # URL = "https://cricclubs.com/LionsSchools/results/qA4wmel_bucef7U4d-93sA?tab=ball_by_ball"
    # URL = "https://cricclubs.com/LionsSchools/results/64VC1qcjq_WqP05KLHpR1Q?tab=ball_by_ball"
    URL = "https://cricclubs.com/LionsSchools/results/9y8-XRCSEPlneYrVYqq4xQ?tab=ball_by_ball"

    async def run():
        files = await scrape_match(URL)
        print("\n📁 Files returned:", files)

    asyncio.run(run())