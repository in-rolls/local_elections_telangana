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

`ward/2019_ward_<district>.csv` (30 files) list 49,823 elected ward members.
They are misaligned against their own header, identically in all 30: `Ward`
holds the literal "Ward", the ward number sits under `Category`, and the
category is glued to the front of the winner's name under `Name`
("ST(W) KOUSALYA PAYAM"). The district is in the filename only. `Status`
says whether the ward was filled unanimously. These came from in-rolls/
local_elections (data/telangana/2019_ward, held there until a89a170), which
parsed them the same way.
"""

import re

import pandas as pd

from local_elections_telangana.parse.common import DATA, SEAT_COLUMNS, reservation

RAW = DATA / "raw" / "2019"
WARDS = "data/raw/2019/ward"
PREFIX = re.compile(r"^(UR|SC|ST|BC)\((G|W)\)\s*(.*)$")
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
            "reserved_raw": raw["Reserved For"].str.strip(),
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
    codes = out["reserved_raw"].map(reservation)
    out["reserved_label"] = [c[0] for c in codes]
    out["reserved_caste"] = [c[1] for c in codes]
    out["reserved_woman"] = [c[2] for c in codes]
    out["unopposed"] = out["unopposed"].astype("Int8")
    out["year"] = out["year"].astype("int16")
    out["reserved_woman"] = out["reserved_woman"].astype("int8")
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
            "reserved_for": "reserved_raw",
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
    codes = out["reserved_raw"].str.strip().map(reservation)
    out["reserved_caste"] = [c[1] for c in codes]
    out["reserved_woman"] = pd.Series([c[2] for c in codes], dtype="int8")
    out.insert(0, "year", pd.Series(2019, index=out.index, dtype="int16"))
    out.insert(0, "state", "Telangana")
    out["source_path"] = CANDIDATES
    out["source_url"] = CANDIDATES_URL
    out["source_locator"] = [f"row {i + 1}" for i in range(len(out))]
    return out


def wards():
    rows = []
    for path in sorted((DATA.parent / WARDS).glob("*.csv")):
        district = path.stem.removeprefix("2019_ward_").strip()
        raw = pd.read_csv(path, dtype=str, keep_default_na=False)
        if set(raw["Ward"].str.strip()) != {"Ward"}:
            raise SystemExit(f"{path.name}: the Ward column is not the literal 'Ward'")
        for i, r in enumerate(raw.itertuples(index=False), start=1):
            got = PREFIX.match(r.Name.strip())
            if not got:
                raise SystemExit(f"{path.name} row {i}: no category prefix: {r.Name!r}")
            category, gender, winner = got.groups()
            rows.append(
                {
                    "district": district,
                    "block": r.Mandal.strip(),
                    "gram_panchayat": r._1.strip(),
                    "ward_no": r.Category.strip(),
                    "reserved_raw": f"{category}({gender})",
                    "winner": re.sub(r"\s+", " ", winner).strip(),
                    "unopposed": int(r.Status.strip().lower() == "unanimous"),
                    "source_path": f"{WARDS}/{path.name}",
                    "source_locator": f"row {i}",
                }
            )
    out = pd.DataFrame(rows)
    codes = out["reserved_raw"].map(reservation)
    out.insert(0, "year", pd.Series(2019, index=out.index, dtype="int16"))
    out.insert(0, "state", "Telangana")
    out["tier"] = "gp_ward"
    out["tier_local"] = "ward member"
    out["reserved_label"] = [c[0] for c in codes]
    out["reserved_caste"] = [c[1] for c in codes]
    out["reserved_woman"] = pd.Series([c[2] for c in codes], dtype="int8")
    out["winner_basis"] = "published"
    out["party"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out["unopposed"] = out["unopposed"].astype("Int8")
    out["script"] = "latin"
    # inferred, as for the 2019 elected listing: the same commission report
    out["source_url"] = ELECTED_URL
    cols = [
        c
        for c in SEAT_COLUMNS
        if c not in ("source_path", "source_url", "source_locator")
    ]
    cols.insert(cols.index("tier"), "ward_no")
    return out[[*cols, "source_path", "source_url", "source_locator"]]


def main():
    (DATA / "2019").mkdir(exist_ok=True)
    seats().to_parquet(DATA / "2019" / "sarpanch_results.parquet", index=False)
    candidates().to_parquet(DATA / "2019" / "sarpanch_candidates.parquet", index=False)
    wards().to_parquet(DATA / "2019" / "ward_results.parquet", index=False)


if __name__ == "__main__":
    main()
