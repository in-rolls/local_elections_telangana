"""Telangana's 2019 sarpanch election, from two published tables.

`2019_gp_sarpanch.csv` lists the 12,018 elected sarpanches with each seat's
reservation code. Its columns are the output of the commission's "Know your PR
representative - Rural" page (tsec.gov.in/knowPRRural.do, "Only Elected
Candidates") with a District column added. Its party column is `IND` on every
row: the polls are formally non-party.

`grampanchayatelectionsdata_2019_sarpanch.csv` is the Telangana Open Data
Portal's candidate-level release (data.telangana.gov.in/dataset/
telangana-gram-panchayat-sarpanch-election-data-2019): every contesting
candidate's votes plus each GP's valid, rejected and tendered votes and NOTA.
It carries GP codes but no winner flag, and uses the district names in force
before 2021 (Warangal Urban rather than Hanumakonda).
"""

import pandas as pd

from local_elections_telangana.parse.common import DATA, SEAT_COLUMNS, reservation

RAW = DATA / "raw" / "2019"
ELECTED = "data/raw/2019/2019_gp_sarpanch.csv"
CANDIDATES = "data/raw/2019/grampanchayatelectionsdata_2019_sarpanch.csv"
ELECTED_URL = "https://tsec.gov.in/knowPRRural.do"
CANDIDATES_URL = (
    "https://data.telangana.gov.in/dataset/"
    "telangana-gram-panchayat-sarpanch-election-data-2019"
)


def squeeze(col):
    """Collapse runs of whitespace; some names carry line breaks."""
    return col.str.replace(r"\s+", " ", regex=True).str.strip()


def seats():
    raw = pd.read_csv(
        DATA.parent / ELECTED, dtype=str, keep_default_na=False, encoding="utf-8-sig"
    )
    out = pd.DataFrame(
        {
            "state": "Telangana",
            "year": 2019,
            "district": squeeze(raw["District"]),
            "block": squeeze(raw["Mandal Name"]),
            "gram_panchayat": squeeze(raw["Grampanchayat Name"]),
            "tier": "gp_head",
            "tier_local": "sarpanch",
            "reservation_raw": raw["Reserved For"].str.strip(),
            "winner": squeeze(raw["Name Of The Contesting Candidate"]),
            "winner_basis": "published",
            "party": raw["Party Affiliation"].str.strip(),
            "unopposed": pd.NA,
            "script": "latin",
            "source_path": ELECTED,
            "source_url": ELECTED_URL,
            # CSV record number after the header, not the physical line
            "source_locator": [f"row {i + 1}" for i in range(len(raw))],
        }
    )
    codes = out["reservation_raw"].map(reservation)
    out["reservation"] = [c[0] for c in codes]
    out["caste_reservation"] = [c[1] for c in codes]
    out["woman_reserved"] = [c[2] for c in codes]
    out["unopposed"] = out["unopposed"].astype("Int8")
    out["year"] = out["year"].astype("int16")
    out["woman_reserved"] = out["woman_reserved"].astype("int8")
    return out[SEAT_COLUMNS]


def candidates():
    raw = pd.read_csv(
        DATA.parent / CANDIDATES,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )
    out = raw.rename(
        columns={
            "district_name": "district",
            "mandal_name": "block",
            "gp_name": "gram_panchayat",
            "gpcode": "gp_code",
            "contestant": "candidate",
            "votes_received": "candidate_votes",
            "reserved_for": "reservation_raw",
            "NOTA": "nota_votes",
        }
    )
    for col in ["district", "block", "gram_panchayat", "candidate"]:
        out[col] = squeeze(out[col])
    for col in [
        "candidate_votes",
        "total_valid_votes",
        "rejected_votes",
        "tendered_votes",
        "nota_votes",
    ]:
        out[col] = pd.to_numeric(out[col], errors="raise").astype("int32")
    codes = out["reservation_raw"].str.strip().map(reservation)
    out["caste_reservation"] = [c[1] for c in codes]
    out["woman_reserved"] = pd.Series([c[2] for c in codes], dtype="int8")
    out.insert(0, "year", pd.Series(2019, index=out.index, dtype="int16"))
    out.insert(0, "state", "Telangana")
    out["source_path"] = CANDIDATES
    out["source_url"] = CANDIDATES_URL
    out["source_locator"] = [f"row {i + 1}" for i in range(len(out))]
    return out


def main():
    (DATA / "2019").mkdir(exist_ok=True)
    seats().to_parquet(DATA / "2019" / "sarpanch_results.parquet", index=False)
    candidates().to_parquet(DATA / "2019" / "sarpanch_candidates.parquet", index=False)


if __name__ == "__main__":
    main()
