"""Screenshot 30 seeded-random 2025 rows as the browser renders the saved page.

The rendering is Chrome's, not BeautifulSoup's, so a parse that misread cells
would show up as a mismatch between sample.csv and the images. Rows are found
with the same locator the parser writes (k-th mandal block, r-th row), so this
checks content, not the locator itself. Needs Google Chrome and playwright:

  uvx --with playwright --with pandas --with pyarrow \
      python -m local_elections_telangana.build.hand_check

The verdict column in data/checks/hand_2025/sample.csv was filled by eye.
"""

import asyncio

import pandas as pd
from playwright.async_api import async_playwright

from local_elections_telangana.parse.common import DATA, RELEASE, ROOT

OUT = DATA / "checks" / "hand_2025"


async def shoot(sample, tmp):
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport={"width": 900, "height": 900})
        current = None
        for i, r in sample.iterrows():
            if r.source_path != current:
                await page.goto(f"file://{ROOT / r.source_path}", wait_until="load")
                current = r.source_path
            k = int(r.source_locator.split("block ")[1].split(",")[0])
            row = int(r.source_locator.split("row ")[1])
            title = page.locator("div.mandal-section-title").nth(k - 1)
            target = await title.get_attribute("data-target")
            await page.evaluate(
                f"document.querySelector('{target}').style.display='table'"
            )
            cell = page.locator(f"{target} tbody tr").nth(row - 1)
            await cell.scroll_into_view_if_needed()
            await title.screenshot(path=tmp / f"{i:02d}_title.png")
            await cell.screenshot(path=tmp / f"{i:02d}_row.png")
        await browser.close()


def main():
    seats = pd.read_parquet(RELEASE / "2025" / "eenadu_results.parquet")
    sample = seats.sample(30, random_state=20251217).reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(shoot(sample, OUT))


if __name__ == "__main__":
    main()
