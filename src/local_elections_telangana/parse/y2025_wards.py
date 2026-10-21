"""Telangana's 2025 gram panchayat ward members, from the commission's report.

The "Know your Public Representative - Rural" form, office "G.P Ward Member"
(collected by collect/tsec.py --wards), gives per mandal one row per ward:
serial, ward name, "Reserved for", the elected candidate and a result status,
under a caption naming the mandal and gram panchayat.

What the report does not give: which wards are reserved for women (the
"Reserved for" cell is the caste category only: BC, SC, ST, UR), the winner's
sex, or votes. reserved_woman is therefore null, not 0. TSEC has not published
wards for every mandal (Adilabad's district report lists 292 of its GPs);
the mandal reports add up to the district reports in every district.

Output: 2025/ward_results.parquet, one row per ward.
"""

import gzip
import html
import re

import pandas as pd

from local_elections_telangana.parse.common import DATA, SEAT_COLUMNS, fold

RAW = "data/raw/2025/tsec"
URL = "https://tsec.gov.in/knowPRRural.se"
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
CAPTION = re.compile(
    r"Name of the Mandal\s*:\s*(?P<mandal>.*?)\s*"
    r"Name of the Gram Panchayat\s*:\s*(?P<gp>.*)",
    re.S,
)
FILE = re.compile(r"district_(\d+)_(\d+)\.html\.gz$")
OPTION = re.compile(r'<option value="(\d+)"[^>]*>([^<]*)</option>')
CASTE = {"UR": "NONE", "SC": "SC", "ST": "ST", "BC": "BC"}
BLANK = "--"


def read(rel):
    return gzip.decompress((DATA.parent / rel).read_bytes()).decode("utf-8", "replace")


def text(cell):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", cell))).strip()


def ward_rows(page):
    """(GP caption, serial, ward name, reserved for, winner, status) per ward."""
    grid = page[page.index('id="GridView1"') :]
    gp, out = None, []
    for row in ROW.findall(grid):
        cells = [text(c) for c in CELL.findall(row)]
        if len(cells) == 1 and (found := CAPTION.search(cells[0])):
            gp = found.group("gp").strip()
        elif len(cells) == 5 and cells[0].isdigit():
            if gp is None:
                raise ValueError("a ward row before any gram panchayat caption")
            out.append((gp, *cells))
    return out


def frame_codes():
    """{(district, mandal, folded GP name): GP code} where the name is unique."""
    rows = []
    for path in sorted((DATA.parent / RAW / "frame").glob("gps_*.html.gz")):
        district, mandal = re.search(r"gps_(\d+)_(\d+)", path.name).groups()
        for code, name in OPTION.findall(read(f"{RAW}/frame/{path.name}")):
            if code != "0":
                rows.append((district, mandal, fold(name), code))
    frame = pd.DataFrame(rows, columns=["d", "m", "g", "code"])
    frame = frame.drop_duplicates(["d", "m", "g"], keep=False)
    return {(r.d, r.m, r.g): r.code for r in frame.itertuples()}


def names():
    """District and mandal names by code, from the frame and report dropdowns."""
    districts, mandals = {}, {}
    for path in sorted((DATA.parent / RAW / "report_E").glob("district_*.html.gz")):
        page = read(f"{RAW}/report_E/{path.name}")
        district = re.search(r"district_(\d+)", path.name).group(1)
        for block, target in (("district_id", districts), ("mandal_id", None)):
            found = re.search(rf'id="{block}"[^>]*>(.*?)</select>', page, re.S)
            for v, n in OPTION.findall(found.group(1) if found else ""):
                if v == "0":
                    continue
                if target is None:
                    mandals[(district, v)] = n.strip()
                else:
                    target[v] = n.strip()
    for path in sorted((DATA.parent / RAW / "frame").glob("mandals_*.html.gz")):
        district = re.search(r"mandals_(\d+)", path.name).group(1)
        for m, n in OPTION.findall(read(f"{RAW}/frame/{path.name}")):
            if m != "0":
                mandals.setdefault((district, m), n.strip())
    return districts, mandals


def build():
    districts, mandals = names()
    codes = frame_codes()
    rows = []
    folder = DATA.parent / RAW / "ward_E" / "by_mandal"
    for path in sorted(folder.glob("district_*.html.gz")):
        if ".nogrid." in path.name:
            continue
        d, m = FILE.search(path.name).groups()
        rel = f"{RAW}/ward_E/by_mandal/{path.name.removesuffix('.gz')}"
        for i, (gp, serial, ward, res, winner, status) in enumerate(
            ward_rows(read(f"{rel}.gz")), 1
        ):
            rows.append(
                {
                    "district_id": d,
                    "mandal_id": m,
                    "gram_panchayat": gp,
                    "ward_no": re.sub(r"(?i)^ward\s*", "", ward),
                    "reserved_raw": res,
                    "winner": None if winner == BLANK else winner,
                    "result_status": None if status == BLANK else status,
                    "source_path": rel,
                    "source_locator": f"results table row {i} (Sl No. {serial})",
                }
            )
    w = pd.DataFrame(rows)
    w["gp_code"] = [
        codes.get((d, m, fold(g)))
        for d, m, g in zip(w.district_id, w.mandal_id, w.gram_panchayat, strict=True)
    ]
    w["reserved_caste"] = w["reserved_raw"].map(CASTE)
    w["reserved_woman"] = pd.Series(pd.NA, index=w.index, dtype="Int8")
    w["reserved_label"] = pd.Series(pd.NA, index=w.index, dtype="string")
    w["unopposed"] = (
        w["result_status"].map({"Unanimous": 1, "Elected": 0}).astype("Int8")
    )
    w["winner_basis"] = pd.Series("published", index=w.index).where(w["winner"].notna())
    w["district"] = w["district_id"].map(districts)
    w["block"] = [
        mandals.get((d, m)) for d, m in zip(w.district_id, w.mandal_id, strict=True)
    ]
    w.insert(0, "year", pd.Series(2025, index=w.index, dtype="int16"))
    w.insert(0, "state", "Telangana")
    w["tier"] = "gp_ward"
    w["tier_local"] = "ward member"
    w["party"] = pd.Series(pd.NA, index=w.index, dtype="string")
    w["script"] = "latin"
    w["source_url"] = URL
    cols = [*SEAT_COLUMNS[:5], "ward_no", *SEAT_COLUMNS[5:-3]]
    extra = ["district_id", "mandal_id", "gp_code", "result_status"]
    return w[cols + extra + SEAT_COLUMNS[-3:]]


def main():
    wards = build()
    (DATA / "2025").mkdir(exist_ok=True)
    wards.to_parquet(DATA / "2025" / "ward_results.parquet", index=False)
    gps = wards.groupby(["district_id", "mandal_id", "gram_panchayat"]).ngroups
    print(f"{len(wards):,} wards in {gps:,} GPs")


if __name__ == "__main__":
    main()
