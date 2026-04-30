import asyncio
import webScraper
import parseDataToJSON 

URL = "https://cricclubs.com/LionsSchools/results/qwfNdZ_0F-BfrvS39oKrCQ?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/APld0Fi3YDjdc8Z23dVqrw?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/8bbdBL0iZKW3XhUx9V4H7w?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/t3o8pqyPNPRdMvMg7QSfBg?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/qA4wmel_bucef7U4d-93sA?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/64VC1qcjq_WqP05KLHpR1Q?tab=ball_by_ball"
# URL = "https://cricclubs.com/LionsSchools/results/9y8-XRCSEPlneYrVYqq4xQ?tab=ball_by_ball"

async def main():
    files = await webScraper.scrape_match(URL)
    print(files)

    parseDataToJSON.generate_match_json(files, "output.json")

    print("✅ Full pipeline completed")

asyncio.run(main())