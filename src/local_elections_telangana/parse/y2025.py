"""Telangana's December 2025 sarpanch election, from Eenadu's results tables.

The commission's per-GP results (tsec.gov.in/knowPRRural.do) cannot be reached
from outside India, so this reads the one complete per-GP compilation that can:
Eenadu's results pages, one per district per polling phase. Each page has a
district heading ("నల్గొండ - 318 / 318 పంచాయతీలు"), then one block per mandal
("మండలం: కట్టంగూర్ (మం) ( 22 / 22 )") holding a three-column table:
panchayat, winner, and the party said to have backed the winner.

What this source is not:
- Not official. Eenadu compiled it while counting ran; the commission's
  results may differ, and the checks compare it against official counts.
- Not a reservation source. It prints no caste or women's quota, so the
  reservation columns are empty for 2025 until the commission's tables (or the
  collectorates' reservation statements) are parsed.
- Not party data in law. Gram panchayat polls are non-party; `backing_party`
  is the newspaper's attribution.

Names are kept in Telugu exactly as printed. Winners are mostly given names
without surnames, as printed.
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from local_elections_telangana.collect.sources_2025 import EENADU, EENADU_DISTRICTS
from local_elections_telangana.parse.common import DATA, SEAT_COLUMNS

RAW = DATA / "raw" / "2025" / "eenadu"

# Eenadu's slug -> the commission's district name (knowPRRural.do district list).
DISTRICT = {
    "adilabad": "Adilabad",
    "bhadradri-kothagudem": "Bhadradri Kothagudem",
    "hanumakonda": "Hanumakonda",
    "jagtial": "Jagtial",
    "jayashankar-bhupalpally": "Jayashankar Bhupalpally",
    "jangaon": "Jangaon",
    "rajanna-sircilla": "Rajanna Sircilla",
    "mahabubabad": "Mahabubabad",
    "mahabubnagar": "Mahabubnagar",
    "mancherial": "Mancherial",
    "medak": "Medak",
    "mulugu": "Mulugu",
    "nagarkurnool": "Nagarkurnool",
    "nalgonda": "Nalgonda",
    "narayanpet": "Narayanpet",
    "nirmal": "Nirmal",
    "nizamabad": "Nizamabad",
    "peddapally": "Peddapalli",
    "rangareddy": "Rangareddy",
    "sangareddy": "Sangareddy",
    "wanaparthy": "Wanaparthy",
    "siddipet": "Siddipet",
    "suryapet": "Suryapet",
    "vikarabad": "Vikarabad",
    "jogulamba-gadwala": "Jogulamba Gadwal",
    "kamareddy": "Kamareddy",
    "karimnagar": "Karimnagar",
    "khammam": "Khammam",
    "kumurambheem-asifabad": "Komaram Bheem Asifabad",
    "warangal": "Warangal",
    "yadadri-bhuvanagiri": "Yadadri Bhuvanagiri",
}

# Party icon file -> code. The icon is read rather than the Telugu label
# because the label's spelling varies (ZWNJ, abbreviations); both are kept.
ICON = {"CONGRESS": "INC", "BRS": "BRS", "BJP": "BJP", "OTHERS": "OTH"}
COUNT = re.compile(r"(\d+)\s*/\s*(\d+)")


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def mandal_name(title):
    text = clean(title.find(string=True, recursive=False) or "")
    text = re.sub(r"^మండలం\s*:\s*", "", text)
    return re.sub(r"\s*\(మం\W*\)\s*$", "", text).strip()


def party_code(cell):
    img = cell.find("img")
    if img is not None:
        stem = img["src"].rsplit("/", 1)[-1].split(".")[0].upper()
        if stem in ICON:
            return ICON[stem]
        return stem
    return pd.NA


def parse_page(phase, slug):
    rel = f"data/raw/2025/eenadu/phase{phase}/{slug}.html"
    soup = BeautifulSoup((DATA.parent / rel).read_text(encoding="utf-8"), "html.parser")
    head = soup.select_one("h2.mandal-ttl")
    declared, total = map(int, COUNT.search(head.get_text()).groups())
    district_te = clean(head.find(string=True, recursive=False))
    rows, mandals = [], []
    for k, title in enumerate(soup.select("div.mandal-section-title"), start=1):
        table = soup.select_one(title["data-target"])
        m_declared, m_total = map(int, COUNT.search(title.span.get_text()).groups())
        block = mandal_name(title)
        mandals.append(
            {
                "district": DISTRICT[slug],
                "phase": phase,
                "block": block,
                "declared": m_declared,
                "total": m_total,
                "source_path": rel,
            }
        )
        for r, tr in enumerate(table.select("tbody tr"), start=1):
            cells = tr.find_all("td")
            if len(cells) != 3:
                raise ValueError(f"{rel} mandal {k} row {r}: {len(cells)} cells")
            rows.append(
                {
                    "district": DISTRICT[slug],
                    "district_printed": district_te,
                    "block": block,
                    "gram_panchayat": clean(cells[0].get_text()),
                    "winner": clean(cells[1].get_text()),
                    "backing_party_printed": clean(cells[2].get_text()),
                    "backing_party": party_code(cells[2]),
                    "phase": phase,
                    "source_path": rel,
                    "source_url": EENADU.format(p=phase, d=slug),
                    "source_locator": f"mandal block {k}, row {r}",
                }
            )
    page = {
        "district": DISTRICT[slug],
        "phase": phase,
        "declared": declared,
        "total": total,
        "rows": len(rows),
        "source_path": rel,
    }
    return rows, mandals, page


def build():
    rows, mandals, pages = [], [], []
    for phase in (1, 2, 3):
        for slug in EENADU_DISTRICTS:
            r, m, p = parse_page(phase, slug)
            rows += r
            mandals += m
            pages.append(p)
    out = pd.DataFrame(rows)
    out.insert(0, "year", pd.Series(2025, index=out.index, dtype="int16"))
    out.insert(0, "state", "Telangana")
    out["tier"] = "gp_head"
    out["tier_local"] = "sarpanch"
    for col in ["reservation", "caste_reservation", "reservation_raw", "party"]:
        out[col] = pd.Series(pd.NA, index=out.index, dtype="string")
    out["woman_reserved"] = pd.Series(pd.NA, index=out.index, dtype="Int8")
    out["unopposed"] = pd.Series(pd.NA, index=out.index, dtype="Int8")
    # A row with no party and no name is a GP whose result the page does not
    # give (no nominations, court stay, or pending); a party with no name is a
    # declared result whose winner Eenadu did not print.
    out["result_declared"] = out["backing_party"].notna()
    out["winner"] = out["winner"].mask(out["winner"].eq(""))
    out["winner_basis"] = pd.Series("published", index=out.index).where(
        out["result_declared"]
    )
    out["script"] = "telugu"
    out["phase"] = out["phase"].astype("int8")
    extra = [
        "district_printed",
        "phase",
        "result_declared",
        "backing_party",
        "backing_party_printed",
    ]
    out = out[SEAT_COLUMNS[:-3] + extra + SEAT_COLUMNS[-3:]]
    return out, pd.DataFrame(mandals), pd.DataFrame(pages)


def main():
    seats, mandals, pages = build()
    (DATA / "2025").mkdir(exist_ok=True)
    seats.to_parquet(DATA / "2025" / "sarpanch_results.parquet", index=False)
    mandals.to_parquet(DATA / "2025" / "eenadu_mandal_counts.parquet", index=False)
    pages.to_parquet(DATA / "2025" / "eenadu_page_counts.parquet", index=False)


if __name__ == "__main__":
    main()
