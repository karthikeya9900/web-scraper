# import asyncio
# from playwright.async_api import async_playwright

# URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"


# async def auto_scroll(page):
#     prev_height = 0

#     while True:
#         curr_height = await page.evaluate("document.body.scrollHeight")

#         if curr_height == prev_height:
#             break

#         prev_height = curr_height
#         await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
#         await asyncio.sleep(1.5)


# async def load_full_innings(page):
#     prev_count = 0

#     while True:
#         await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
#         await asyncio.sleep(1.2)

#         balls = page.locator("div.border-b.pb-2")
#         count = await balls.count()

#         print(f"Loaded balls: {count}")

#         if count == prev_count:
#             print("✅ Innings fully loaded")
#             break

#         prev_count = count


# async def wait_for_innings_change(page, old_html):
#     print("👀 Waiting for innings change (DOM watcher)...")

#     await page.wait_for_function(
#    """(old) => {
#         const el = document.querySelector('div.border-b.pb-2')?.parentElement;
#         return el && el.innerHTML !== old;
#     }""" ,
#     arg=old_html,
#     timeout=60000
# )

#     print("🔄 Innings change detected!")


# async def main():
#     async with async_playwright() as p:
#         browser = await p.chromium.launch(headless=False)
#         page = await browser.new_page()
#         # page.on("response", lambda r: print("🌐", r.status, r.url))

#         print("Opening page...")
#         await page.goto(URL)
#         await page.wait_for_load_state("networkidle")

#         print("Clicking Ball by Ball tab...")
#         await page.click("text=Ball by Ball")

#         # data = await page.evaluate("() => window")
#         # print(data)

#         keys = await page.evaluate("() => Object.keys(window)")
#         print(keys)

#         await page.wait_for_selector("div.border-b.pb-2")

#         # =========================
#         # INNINGS 1
#         # =========================
#         print("\n👉 Load first innings (manually select if needed)...")

#         await load_full_innings(page)

#         # capture container HTML signature
#         container = page.locator("div.border-b.pb-2").first.locator("..")
#         old_html = await container.inner_html()

#         html1 = await page.content()
#         with open("innings_1.html", "w", encoding="utf-8") as f:
#             f.write(html1)

#         print("✅ Saved innings_1.html")

#         # =========================
#         # WAIT FOR INNINGS CHANGE
#         # =========================
#         print("\n👉 Now switch innings in UI (script will detect automatically)")

#         await wait_for_innings_change(page, old_html)

#         # =========================
#         # INNINGS 2
#         # =========================
#         print("Loading second innings...")

#         await load_full_innings(page)

#         html2 = await page.content()
#         with open("innings_2.html", "w", encoding="utf-8") as f:
#             f.write(html2)

#         print("✅ Saved innings_2.html")

#         await browser.close()


# asyncio.run(main())


import asyncio
from playwright.async_api import async_playwright

# URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"
URL = "https://cricclubs.com/LionsSchools/results/spa57Bk3BkEDPo9jIEdSLQ?tab=ball_by_ball"


async def auto_scroll(page):
    prev = 0
    while True:
        curr = await page.evaluate("document.body.scrollHeight")
        if curr == prev:
            break
        prev = curr
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


async def get_innings_options(page):
    container = page.locator("div.flex.flex-col.md\\:w-\\[70\\%\\]")

    await container.wait_for()

    dropdown = container.locator("button").first
    await dropdown.click()

    await asyncio.sleep(1)

    options = container.locator("ul li")

    texts = []
    for i in range(await options.count()):
        txt = (await options.nth(i).inner_text()).strip()
        if txt and "Player" not in txt:
            texts.append(txt)

    print("Detected innings (teams):", texts)
    return texts

async def select_innings(page, team_name):
    print(f"\n👉 Selecting innings: {team_name}")

    container = page.locator("div.flex.flex-col.md\\:w-\\[70\\%\\]")

    # Open dropdown
    dropdown = container.locator("button").first
    await dropdown.click()

    # Wait for dropdown to be visible (IMPORTANT)
    await page.wait_for_selector("li.ant-dropdown-menu-item:visible", timeout=5000)

    # Target ONLY visible dropdown items
    option = page.locator("li.ant-dropdown-menu-item:visible", has_text=team_name)

    # 🔥 Force click (bypass animation/stability issues)
    await option.first.click(force=True)

    await asyncio.sleep(2)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print("Opening page...")
        await page.goto(URL)
        await page.wait_for_load_state("networkidle")

        print("Clicking Ball by Ball tab...")
        await page.click("text=Ball by Ball")

        await page.wait_for_selector("div.border-b.pb-2")

        # =========================
        # GET TEAM NAMES (INNINGS)
        # =========================
        innings_list = await get_innings_options(page)

        # =========================
        # LOOP THROUGH EACH TEAM
        # =========================
        for idx, team in enumerate(innings_list):
            await select_innings(page, team)

            await load_full_innings(page)
            await auto_scroll(page)

            html = await page.content()

            filename = f"innings_{idx+1}_{team.replace(' ', '_')}.html"

            with open(filename, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"✅ Saved {filename}")

        await browser.close()


asyncio.run(main())