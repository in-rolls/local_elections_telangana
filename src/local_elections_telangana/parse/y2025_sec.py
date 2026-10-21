"""Telangana's December 2025 sarpanch election, from the commission's own reports.

The State Election Commission's "Know your Public Representative - Rural" form
(tsec.gov.in/knowPRRural.do, collected by collect/tsec.py) gives two reports
per district and per mandal:

- E, "Only Elected Candidates": one row per GP with its reservation code
  (e.g. `ST(W)`) and the elected sarpanch, in Latin script.
- A, "All Contested Candidates": per GP a caption row ("Gram Panchayat : X ,
  Reserved for : ST(W) , Total Vaild Votes : n , ...") and one row per
  candidate with votes and a status ("Elected" or "--").

The district reports name no mandal, and GP names repeat within a district,
so seats are read from the mandal reports; the district reports are kept as an
independent count of the same GPs. The GP dropdown lists (frame/gps_*.html)
give the commission's GP code within the mandal.

Outputs:
- 2025/sarpanch_results.parquet: one row per GP in the A or E mandal reports.
- 2025/sarpanch_candidates.parquet: one row per candidate in the A reports.
"""

import gzip
import html
import re

import pandas as pd

from local_elections_telangana.parse.common import (
    DATA,
    SEAT_COLUMNS,
    fold,
    reservation,
)

RAW = "data/raw/2025/tsec"
URL = "https://tsec.gov.in/knowPRRural.se"
SELECT = re.compile(r'id="{}"[^>]*>(.*?)</select>', re.S)
OPTION = re.compile(r'<option value="(\d+)"[^>]*>([^<]*)</option>')
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
COMMENT = re.compile(r"<!--.*?-->", re.S)
TAG = re.compile(r"<[^>]+>")
CAPTION = re.compile(
    r"Gram Panchayat\s*:\s*(?P<gp>.*?)\s*,\s*Reserved for\s*:\s*(?P<res>\S+)\s*,"
    r"\s*Total Vaild Votes\s*:\s*(?P<valid>\d+)\s*,\s*Rejected Votes\s*:\s*"
    r"(?P<rejected>\d+)\s*,\s*Tendered Votes\s*:\s*(?P<tendered>\d+)\s*,\s*"
    r"NOTA Votes\s*:\s*(?P<nota>\d+)",
    re.S,
)
FILE = re.compile(r"district_(\d+)(?:_(\d+))?\.html\.gz$")


def read(rel):
    return gzip.decompress((DATA.parent / rel).read_bytes()).decode("utf-8", "replace")


def text(cell):
    cell = TAG.sub(" ", COMMENT.sub(" ", cell))
    return re.sub(r"\s+", " ", html.unescape(cell)).strip()


def dropdown(page, name):
    found = SELECT.pattern.format(name)
    got = re.search(found, page, re.S)
    if not got:
        return {}
    return {v: n.strip() for v, n in OPTION.findall(got.group(1)) if v != "0"}


def report_files(kind, by_mandal):
    folder = DATA.parent / RAW / f"report_{kind}"
    if by_mandal:
        folder = folder / "by_mandal"
    for path in sorted(folder.glob("district_*.html.gz")):
        if ".nogrid." in path.name:
            continue
        district, mandal = FILE.search(path.name).groups()
        yield district, mandal, f"{RAW}/{path.relative_to(DATA.parent / RAW)}"


def names():
    """District and mandal names by code, from the forms' own dropdowns.

    Mandal names come from both the getMandal lists and the report pages'
    dropdowns: each omits mandals the other has.
    """
    districts, mandals = {}, {}
    for district, _, rel in report_files("E", by_mandal=False):
        page = read(rel)
        districts.update(dropdown(page, "district_id"))
        for m, n in dropdown(page, "mandal_id").items():
            mandals[(district, m)] = n
    for path in sorted((DATA.parent / RAW / "frame").glob("mandals_*.html.gz")):
        district = re.search(r"mandals_(\d+)", path.name).group(1)
        page = read(f"{RAW}/frame/{path.name}")
        for m, n in OPTION.findall(page):
            if m != "0":
                mandals.setdefault((district, m), n.strip())
    return districts, mandals


def elected_rows(page):
    """(serial, GP, reservation code, winner) per row of an E report."""
    grid = page[page.index('id="GridView1"') :]
    out = []
    for row in ROW.findall(grid):
        cells = [text(c) for c in CELL.findall(row)]
        if len(cells) == 4 and cells[0].isdigit():
            out.append(cells)
    return out


def candidate_rows(page):
    """GP captions and the candidate rows under each, from an A report."""
    grid = page[page.index('id="GridView1"') :]
    gps, cands = [], []
    for row in ROW.findall(grid):
        cells = CELL.findall(row)
        if len(cells) == 1 and not text(cells[0]):
            continue  # spacer row
        if len(cells) == 1:
            got = CAPTION.search(text(cells[0]))
            if not got:
                raise ValueError(f"unreadable caption: {text(cells[0])[:120]!r}")
            gps.append(got.groupdict())
        elif len(cells) == 4 and text(cells[0]).isdigit():
            if not gps:
                raise ValueError("candidate row before any GP caption")
            status = text(cells[3])
            if status not in {"Elected", "--"}:
                raise ValueError(f"unknown result status {status!r}")
            cands.append(
                {
                    "gp_index": len(gps) - 1,
                    "serial": int(text(cells[0])),
                    "candidate": text(cells[1]),
                    "candidate_votes": int(text(cells[2])),
                    "elected": status == "Elected",
                }
            )
    return gps, cands


def frame_codes():
    """{(district, mandal, folded GP name): GP code}, ambiguous names dropped."""
    rows = []
    for path in sorted((DATA.parent / RAW / "frame").glob("gps_*.html.gz")):
        district, mandal = re.search(r"gps_(\d+)_(\d+)", path.name).groups()
        for code, name in OPTION.findall(read(f"{RAW}/frame/{path.name}")):
            if code != "0":
                rows.append((district, mandal, fold(name), code))
    frame = pd.DataFrame(rows, columns=["d", "m", "g", "code"])
    frame = frame.drop_duplicates(["d", "m", "g"], keep=False)
    return {(r.d, r.m, r.g): r.code for r in frame.itertuples()}, len(rows)


def occurrence(df, key):
    """Number each repeat of a key, so repeated GP names pair up in order."""
    return df.groupby(key, sort=False).cumcount()


def build():
    districts, mandals = names()
    codes, _ = frame_codes()

    e_rows = []
    for d, m, rel in report_files("E", by_mandal=True):
        for i, (serial, gp, res, winner) in enumerate(elected_rows(read(rel)), 1):
            e_rows.append(
                {
                    "district_id": d,
                    "mandal_id": m,
                    "gram_panchayat": gp,
                    "reserved_raw": res,
                    "winner": winner,
                    "e_path": rel,
                    "e_locator": f"results table row {i} (Sl No. {serial})",
                }
            )
    elected = pd.DataFrame(e_rows)

    a_gps, a_cands = [], []
    for d, m, rel in report_files("A", by_mandal=True):
        gps, cands = candidate_rows(read(rel))
        base = len(a_gps)
        for k, g in enumerate(gps, 1):
            a_gps.append(
                {
                    "district_id": d,
                    "mandal_id": m,
                    "gram_panchayat": g["gp"],
                    "reserved_raw_a": g["res"],
                    "total_valid_votes": int(g["valid"]),
                    "rejected_votes": int(g["rejected"]),
                    "tendered_votes": int(g["tendered"]),
                    "nota_votes": int(g["nota"]),
                    "a_path": rel,
                    "a_locator": f"GP caption {k}",
                }
            )
        for c in cands:
            a_cands.append({**c, "gp_row": base + c.pop("gp_index")})
    contested = pd.DataFrame(a_gps)
    cands = pd.DataFrame(a_cands)
    summary = cands.groupby("gp_row").agg(
        candidates=("candidate", "size"),
        elected_count=("elected", "sum"),
    )
    winners = cands[cands["elected"]].drop_duplicates("gp_row", keep=False)
    summary["elected_name"] = winners.set_index("gp_row")["candidate"]
    contested = contested.join(summary, how="left")

    key = ["district_id", "mandal_id", "g"]
    elected["g"] = elected["gram_panchayat"].map(fold)
    contested["g"] = contested["gram_panchayat"].map(fold)
    elected["n"] = occurrence(elected, key)
    contested["n"] = occurrence(contested, key)
    seats = elected.merge(
        contested.rename(columns={"gram_panchayat": "gp_a"}),
        on=[*key, "n"],
        how="outer",
        indicator="in_reports",
    )
    seats["gram_panchayat"] = seats["gram_panchayat"].fillna(seats["gp_a"])
    seats["in_reports"] = seats["in_reports"].map(
        {"both": "both", "left_only": "elected_only", "right_only": "candidates_only"}
    )
    # The E report prints a few GPs twice (same GP, same winner, sometimes
    # spelled differently); the A report lists them once. Keep the row that
    # pairs with the A report and mark it.
    seats["gp_code"] = [
        codes.get((d, m, g))
        for d, m, g in zip(seats.district_id, seats.mandal_id, seats.g, strict=True)
    ]
    gp_key = ["district_id", "mandal_id", "gp_code"]
    paired = seats[seats["in_reports"].eq("both")].set_index(gp_key).index
    repeat = seats["in_reports"].eq("elected_only") & seats.set_index(
        gp_key
    ).index.isin(paired)
    twice = seats.loc[repeat].set_index(gp_key).index
    seats = seats[~repeat].reset_index(drop=True)
    seats["listed_twice"] = seats["in_reports"].eq("both") & seats.set_index(
        gp_key
    ).index.isin(twice)
    seats["reserved_raw"] = seats["reserved_raw"].fillna(seats["reserved_raw_a"])
    codes_ = seats["reserved_raw"].map(reservation)
    seats["reserved_label"] = [c[0] for c in codes_]
    seats["reserved_caste"] = [c[1] for c in codes_]
    seats["reserved_woman"] = pd.Series([c[2] for c in codes_], dtype="int8")
    seats["district"] = seats["district_id"].map(districts)
    seats["block"] = [
        mandals.get((d, m))
        for d, m in zip(seats.district_id, seats.mandal_id, strict=True)
    ]
    single = seats["candidates"].eq(1) & seats["total_valid_votes"].eq(0)
    seats["unopposed"] = single.astype("Int8").where(seats["candidates"].notna())
    seats["result_declared"] = seats["winner"].notna()
    seats["winner_basis"] = pd.Series("published", index=seats.index).where(
        seats["result_declared"]
    )
    seats.insert(0, "year", pd.Series(2025, index=seats.index, dtype="int16"))
    seats.insert(0, "state", "Telangana")
    seats["tier"] = "gp_head"
    seats["tier_local"] = "sarpanch"
    seats["party"] = pd.Series(pd.NA, index=seats.index, dtype="string")
    seats["script"] = "latin"
    seats["source_path"] = seats["e_path"].fillna(seats["a_path"])
    seats["source_url"] = URL
    seats["source_locator"] = seats["e_locator"].fillna(seats["a_locator"])
    for col in ["candidates", "elected_count"]:
        seats[col] = seats[col].astype("Int16")
    for col in ["total_valid_votes", "rejected_votes", "tendered_votes", "nota_votes"]:
        seats[col] = seats[col].astype("Int32")
    extra = [
        "district_id",
        "mandal_id",
        "gp_code",
        "result_declared",
        "in_reports",
        "listed_twice",
        "reserved_raw_a",
        "candidates",
        "elected_count",
        "elected_name",
        "total_valid_votes",
        "rejected_votes",
        "tendered_votes",
        "nota_votes",
        "a_path",
        "a_locator",
    ]
    # page order: by report file, then row position on the page
    seats["_row"] = seats["source_locator"].str.extract(r"(\d+)")[0].astype(int)
    seats = seats.sort_values(["district_id", "source_path", "_row"])
    seats = seats[SEAT_COLUMNS[:-3] + extra + SEAT_COLUMNS[-3:]].reset_index(drop=True)

    gp = contested[
        ["district_id", "mandal_id", "gram_panchayat", "a_path", "a_locator"]
    ]
    cands = cands.join(gp, on="gp_row")
    cands["district"] = cands["district_id"].map(districts)
    cands["block"] = [
        mandals.get((d, m))
        for d, m in zip(cands.district_id, cands.mandal_id, strict=True)
    ]
    cands.insert(0, "year", pd.Series(2025, index=cands.index, dtype="int16"))
    cands.insert(0, "state", "Telangana")
    cands["candidate_votes"] = cands["candidate_votes"].astype("int32")
    cands["serial"] = cands["serial"].astype("int32")
    cands = cands.rename(columns={"a_path": "source_path"})
    cands["source_url"] = URL
    cands["source_locator"] = (
        cands["a_locator"] + ", candidate Sl No. " + cands["serial"].astype(str)
    )
    cands = cands[
        [
            "state",
            "year",
            "district",
            "block",
            "gram_panchayat",
            "district_id",
            "mandal_id",
            "serial",
            "candidate",
            "candidate_votes",
            "elected",
            "source_path",
            "source_url",
            "source_locator",
        ]
    ]
    return seats, cands


def district_report_counts():
    """GP rows per district in the district-level E and A reports."""
    out = {}
    for kind in ("E", "A"):
        for d, _, rel in report_files(kind, by_mandal=False):
            page = read(rel)
            if kind == "E":
                out[(kind, d)] = len(elected_rows(page))
            else:
                out[(kind, d)] = len(candidate_rows(page)[0])
    return out


def main():
    seats, cands = build()
    (DATA / "2025").mkdir(exist_ok=True)
    seats.to_parquet(DATA / "2025" / "sarpanch_results.parquet", index=False)
    cands.to_parquet(DATA / "2025" / "sarpanch_candidates.parquet", index=False)


if __name__ == "__main__":
    main()
