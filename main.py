import asyncio
import webScraper
import parseDataToJSON   # your first file

URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"

async def main():
    files = await webScraper.scrape_match(URL)

    parseDataToJSON.generate_match_json(files, "output.json")

    print("✅ Full pipeline completed")

asyncio.run(main())