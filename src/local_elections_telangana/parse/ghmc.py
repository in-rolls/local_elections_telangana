"""Parse retained GHMC sources offline; preserve source-specific records."""

import csv
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

import pdfplumber
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data/raw/urban/ghmc"
RELEASE = ROOT / "data/release/urban/ghmc"
WINNERS = ROOT / (
    "data/raw/tsec_docs/files/StatisticalRep/MC/2024/"
    "elected_ward_members_of_ghmc,2020_2053.pdf"
)
REPORT = ROOT / (
    "data/raw/tsec_docs/files/StatisticalRep/ElectionReport/2021/"
    "Election_Report-GHMC-2020-Final-Madhavi_1639.pdf"
)
TABLES = {
    "candidates_2016": "ghmc_candidates_2016",
    "candidate_profiles_2020": "ghmc_candidate_profiles_2020",
    "candidate_returns_2020": "ghmc_candidate_returns_2020",
    "winners": "ghmc_winners",
}


def descriptor(name):
    return json.loads((ROOT / "schemas" / f"{TABLES[name]}.json").read_text())


def arrow_schema(name):
    types = {
        "string": pa.string(),
        "int8": pa.int8(),
        "int16": pa.int16(),
        "int32": pa.int32(),
        "bool": pa.bool_(),
    }
    return pa.schema(
        [
            pa.field(
                f["name"],
                types[f["arrowType"]],
                nullable=not f.get("constraints", {}).get("required", False),
            )
            for f in descriptor(name)["fields"]
        ]
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value):
    return " ".join((value or "").split())


def reservation(value):
    v = re.sub(r"[\s()]", "", value).upper()
    codes = {
        "UR": "NONE",
        "URG": "NONE",
        "URW": "NONE",
        "UNRESERVED": "NONE",
        "WOMENGENERAL": "NONE",
        "BC": "BC",
        "BCG": "BC",
        "BCW": "BC",
        "BCGENERAL": "BC",
        "BCWOMEN": "BC",
        "SC": "SC",
        "SCG": "SC",
        "SCW": "SC",
        "SCGENERAL": "SC",
        "SCWOMEN": "SC",
        "ST": "ST",
        "STG": "ST",
        "STW": "ST",
        "STGENERAL": "ST",
        "STWOMEN": "ST",
    }
    if v not in codes:
        raise ValueError(f"Unknown reservation: {value}")
    return codes[v], int("W" in v)


def verify_sources():
    with (ROOT / "data/raw/fetch_log.csv").open() as stream:
        receipts = {r["path"]: r for r in csv.DictReader(stream)}
    for path in [
        WINNERS,
        REPORT,
        RAW / "candidate_results_2016.pdf",
        RAW / "candidate_results_2020.pdf",
        RAW / "candidate_profiles_2020.pdf",
    ]:
        receipt = receipts[str(path.relative_to(ROOT))]
        if sha(path) != receipt["sha256"] or path.stat().st_size != int(
            receipt["bytes"]
        ):
            raise ValueError(f"Source bytes changed: {path}")


def base(path, year, page, row_no, raw):
    return {
        "year": year,
        "body": "Greater Hyderabad Municipal Corporation",
        "source_path": str(path.relative_to(ROOT)),
        "source_page": page,
        "source_row": row_no,
        "raw_record": json.dumps(raw, ensure_ascii=False),
    }


def read_candidate_name_cells(path, rows):
    """Read complete PDF name cells, including wrapped lines above/below totals."""
    by_page = defaultdict(list)
    for row in rows:
        by_page[row["source_page"]].append(row)
    with pdfplumber.open(path) as pdf:
        for page_no, records in by_page.items():
            page = pdf.pages[page_no - 1]
            words = page.extract_words()
            for row in records:
                line = json.loads(row["raw_record"])
                serial = line.split()[0]
                anchors = [
                    word
                    for word in words
                    if word["text"] == serial and word["x0"] < 105
                ]
                if len(anchors) != 1:
                    raise ValueError("Candidate serial does not identify one PDF row")
                anchor = anchors[0]
                cy = (anchor["top"] + anchor["bottom"]) / 2
                cx = (anchor["x0"] + anchor["x1"]) / 2
                ballot = [
                    word
                    for word in words
                    if word["text"] == str(row["candidate_no"])
                    and anchor["x1"] < word["x0"] < 180
                    and abs((word["top"] + word["bottom"]) / 2 - cy) < 3
                ]
                party = [
                    word
                    for word in words
                    if word["text"] == row["party"]
                    and word["x0"] > 200
                    and abs((word["top"] + word["bottom"]) / 2 - cy) < 3
                ]
                if len(ballot) != 1 or len(party) != 1:
                    raise ValueError("Ballot/party anchors do not identify one PDF row")
                xs = [
                    edge["x0"]
                    for edge in page.vertical_edges
                    if edge["top"] < cy < edge["bottom"] and 50 < edge["x0"] < 550
                ]
                ys = [
                    edge["top"]
                    for edge in page.horizontal_edges
                    if edge["x0"] < cx < edge["x1"]
                ]
                box = (
                    min(x for x in xs if x > ballot[0]["x1"] + 1),
                    max(y for y in ys if y < anchor["top"]),
                    max(x for x in xs if x < party[0]["x0"] - 1),
                    min(y for y in ys if y > anchor["bottom"]),
                )
                cell = page.crop(box).extract_text()
                if not normalize(cell):
                    raise ValueError("Empty PDF candidate-name cell")
                row["raw_record"] = json.dumps(
                    {
                        "result_line": line,
                        "name_cell": cell,
                        "name_cell_bbox": list(box),
                        "name_from_numeric_line": row["candidate_name"],
                    },
                    ensure_ascii=False,
                )
                row["candidate_name"] = normalize(cell)


def parse_2016(path):
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows, current = [], None
    for page, block in enumerate(text.split("\f"), 1):
        for line_no, line in enumerate(block.splitlines(), 1):
            m = re.search(
                r"Ward\s*:\s*(\d+)-(.+?)\s*,\s*Reserved [Ff]or\s*:\s*([^,]+)", line
            )
            if m:
                current = (int(m[1]), m[2].strip(), m[3].strip())
                continue
            m = re.match(
                r"^\s*(\d+)\s+(\d+)\s+(.+?)\s{2,}(\S+)\s+(\d+)\s*(Winner)?\s*$", line
            )
            if not m:
                if re.match(r"^\s*\d+\s+\d+\s+", line):
                    raise ValueError(f"Unparsed candidate row {page}:{line_no}")
                continue
            if current is None:
                raise ValueError("Candidate before ward_no header")
            caste, woman = reservation(current[2])
            rows.append(
                dict(
                    base(path, 2016, page, line_no, line),
                    ward_no=current[0],
                    ward_name_raw=current[1],
                    candidate_no=int(m[2]),
                    candidate_name=m[3].strip(),
                    party=m[4],
                    votes=int(m[5]),
                    elected=bool(m[6]),
                    reserved_raw=current[2],
                    reserved_caste=caste,
                    reserved_woman=woman,
                )
            )
    if len(rows) != 1333:
        raise ValueError(f"Expected1333 candidates, got {len(rows)}")
    validate(rows, 150)
    read_candidate_name_cells(path, rows)
    return rows


def parse_2020_winners(path):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            bounds = sorted(
                {
                    e["top"]
                    for e in page.horizontal_edges
                    if e["x0"] < 73 and e["x1"] > 540
                }
                | {72, 780}
            )
            serials = [
                w
                for w in page.extract_words()
                if 76 < w["x0"] < 97
                and w["text"].isdigit()
                and (page_no > 1 or w["top"] > 171)
            ]
            bottom = page.find_tables()[0].bbox[3]
            for word in serials:
                y0 = max(y for y in bounds if y < word["top"])
                y1 = min(min(y for y in bounds if y > word["bottom"]), bottom)
                columns = [71.3, 100.8, 216, 293, 399.1, 455.9, 547.2]
                c = [
                    normalize(page.crop((a, y0, b, y1)).extract_text())
                    for a, b in pairwise(columns)
                ]
                ward_no = int(c[0])
                m = re.match(r"(\d+)\s*[-\u2013]\s*(.+)", c[1])
                if m is None or int(m[1]) != ward_no or c[4] not in {"Male", "Female"}:
                    raise ValueError(f"Malformed winner row: {c}")
                caste, woman = reservation(c[2])
                rows.append(
                    dict(
                        base(path, 2020, page_no, ward_no, c),
                        ward_no=ward_no,
                        ward_name_raw=m[2],
                        candidate_name=c[3],
                        party=c[5],
                        elected=True,
                        candidate_woman_raw=c[4],
                        candidate_woman=int(c[4] == "Female"),
                        reserved_raw=c[2],
                        reserved_caste=caste,
                        reserved_woman=woman,
                    )
                )
    validate(rows, 150)
    return rows


def parse_2020_candidates(path, winner_frame, profiles):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for row_no, c in enumerate(table, 1):
                    if len(c) != 17:
                        raise ValueError(f"Unexpected columns at page{page_no}: {c}")
                    if not c[11] or not c[11].isdigit() or c[12] == "13":
                        continue
                    rows.append(
                        dict(
                            base(path, 2020, page_no, row_no, c),
                            ward_label_cell_raw=normalize(c[2]) or None,
                            candidate_no=int(c[11]),
                            candidate_name=normalize(c[12]),
                            party=normalize(c[14]),
                            votes=int(c[13]),
                            elected=normalize(c[15]) == "Elected",
                        )
                    )
    groups = []
    for row in rows:
        if row["candidate_no"] == 1:
            groups.append([])
        if not groups:
            raise ValueError("Return does not start with candidate1")
        groups[-1].append(row)
    profile_wards = defaultdict(set)
    for row in profiles:
        profile_wards[name_key(row["candidate_name"])].add(row["ward_no"])
    linked = []
    for group in groups:
        matches = [
            profile_wards[name_key(row["candidate_name"])]
            for row in group
            if profile_wards[name_key(row["candidate_name"])]
        ]
        possible = set.intersection(*matches) if matches else set()
        if len(possible) != 1:
            raise ValueError(
                "Candidate block does not identify exactly one profile ward_no"
            )
        ward_no = possible.pop()
        source = winner_frame[ward_no]
        for row in group:
            printed = re.search(r"Ward\s*(\d+)\b", row["ward_label_cell_raw"] or "")
            if printed and int(printed[1]) != ward_no:
                raise ValueError(
                    "Profile-linked ward_no conflicts with printed return label"
                )
            row.update(
                ward_no=ward_no,
                ward_name_raw=source["ward_name_raw"],
                reserved_raw=source["reserved_raw"],
                reserved_caste=source["reserved_caste"],
                reserved_woman=source["reserved_woman"],
            )
            linked.append(row)
    if (
        len(linked) != 1117
        or len({(r["ward_no"], r["candidate_no"]) for r in linked}) != 1117
    ):
        raise ValueError("Candidate return keys are incomplete or duplicated")
    if {r["ward_no"] for r in linked} != set(range(1, 151)) - {136}:
        raise ValueError("Unexpected return ward_no coverage")
    if len(groups) != 149 or sum(r["elected"] for r in linked) != 149:
        raise ValueError("Expected149 return blocks and elected candidates")
    return linked


def name_key(value):
    return re.sub(r"\W", "", value).casefold()


def parse_profiles(path):
    rows = []
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for c in table:
                    if not (c[0] or "").isdigit():
                        continue
                    if len(c) != 14 or c[7] not in {"Male", "Female"}:
                        raise ValueError(f"Malformed candidate profile: {c}")
                    m = re.fullmatch(r"Ward\s+(\d+)\s*-\s*(.+)", normalize(c[2]))
                    if m is None:
                        raise ValueError(f"Unknown profile ward_no: {c[2]}")
                    caste, woman = reservation(c[3])
                    rows.append(
                        dict(
                            base(path, 2020, page_no, int(c[0]), c),
                            ward_no=int(m[1]),
                            ward_name_raw=m[2],
                            candidate_no=int(c[4]),
                            candidate_name=normalize(c[5]),
                            party=normalize(c[6]),
                            candidate_woman_raw=c[7],
                            candidate_woman=int(c[7] == "Female"),
                            candidate_age=int(c[9])
                            if c[9] and c[9].isdigit()
                            else None,
                            candidate_education=normalize(c[12]) or None,
                            candidate_occupation=normalize(c[13]) or None,
                            candidate_caste_raw=normalize(c[8]),
                            candidate_caste=reservation(c[8])[0],
                            reserved_raw=normalize(c[3]),
                            reserved_caste=caste,
                            reserved_woman=woman,
                        )
                    )
    if (
        len(rows) != 1122
        or len({(r["ward_no"], r["candidate_no"]) for r in rows}) != 1122
    ):
        raise ValueError("Incomplete or duplicated candidate profile frame")
    if {r["ward_no"] for r in rows} != set(range(1, 151)):
        raise ValueError("Incomplete profile ward_no frame")
    return rows


def validate(rows, wards):
    if {r["ward_no"] for r in rows} != set(range(1, wards + 1)):
        raise ValueError("Incomplete ward_no frame")
    winners = [r for r in rows if r["elected"]]
    if len(winners) != wards or len({r["ward_no"] for r in winners}) != wards:
        raise ValueError("Expected exactly one winner per ward_no")


def build(release=RELEASE):
    verify_sources()
    first = parse_2016(RAW / "candidate_results_2016.pdf")
    second = parse_2020_winners(WINNERS)
    profiles = parse_profiles(RAW / "candidate_profiles_2020.pdf")
    candidates = parse_2020_candidates(
        RAW / "candidate_results_2020.pdf", {r["ward_no"]: r for r in second}, profiles
    )
    outputs = {
        "candidate_profiles_2020": profiles,
        "candidates_2016": first,
        "winners": [dict(r) for r in first if r["elected"]] + [dict(r) for r in second],
        "candidate_returns_2020": candidates,
    }
    release.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for records in outputs.values():
        for r in records:
            if r["source_path"] not in inputs:
                inputs[r["source_path"]] = sha(ROOT / r["source_path"])
            r["reserved_source_path"] = (
                str(WINNERS.relative_to(ROOT))
                if r["source_path"].endswith("candidate_results_2020.pdf")
                else r["source_path"]
            )
            r["source_sha256"] = inputs[r["source_path"]]
            is_return = r["source_path"].endswith("candidate_results_2020.pdf")
            r["ward_source_path"] = (
                str((RAW / "candidate_profiles_2020.pdf").relative_to(ROOT))
                if is_return
                else r["source_path"]
            )
            r["ward_link_basis"] = (
                "unique_profile_ward_for_candidate_block"
                if is_return
                else "printed_ward_identifier"
            )
    for name, records in outputs.items():
        for row in records:
            row["ward_no"] = str(row["ward_no"])
            if row.get("candidate_no") is not None:
                row["candidate_no"] = str(row["candidate_no"])
            row["reserved_basis"] = (
                "official_winner_table"
                if row["source_path"].endswith("candidate_results_2020.pdf")
                else "source_cell"
            )
            if name == "winners":
                row["winner"] = row.pop("candidate_name")
                row["winner_woman_raw"] = row.pop("candidate_woman_raw", None)
                row["winner_woman"] = row.pop("candidate_woman", None)
                row.pop("candidate_no", None)
                row.pop("elected", None)
        table = pa.Table.from_pylist(records, schema=arrow_schema(name))
        pq.write_table(table, release / f"{name}.parquet")
        if not table.equals(pq.read_table(release / f"{name}.parquet")):
            raise ValueError("Parquet round trip changed values")
    prior = {str(r["ward_no"]): r for r in first if r["elected"]}
    differences = [
        r["ward_no"]
        for r in second
        if (r["reserved_caste"], r["reserved_woman"])
        != (
            prior[str(r["ward_no"])]["reserved_caste"],
            prior[str(r["ward_no"])]["reserved_woman"],
        )
    ]
    profile = {
        "candidates_2016": len(first),
        "candidate_profiles_2020": len(profiles),
        "candidate_sex_2020": dict(Counter(r["candidate_woman_raw"] for r in profiles)),
        "winners_2020": len(second),
        "candidate_returns_2020": len(candidates),
        "candidate_return_wards_2020": len({r["ward_no"] for r in candidates}),
        "elected_in_candidate_return_2020": sum(r["elected"] for r in candidates),
        "women_winners_2020": sum(r["candidate_woman"] for r in second),
        "women_reserved_2020": sum(r["reserved_woman"] for r in second),
        "reservation_disagreements_2016_2020": differences,
        "winner_party_2020": dict(Counter(r["party"] for r in second)),
        "input_sha256": inputs,
    }
    name_checks = []
    for row in first:
        raw = json.loads(row["raw_record"])
        if raw["name_from_numeric_line"] != row["candidate_name"]:
            name_checks.append(
                {
                    "ward_no": row["ward_no"],
                    "candidate_no": row["candidate_no"],
                    "source_page": row["source_page"],
                    "source_row": row["source_row"],
                    "line_name": raw["name_from_numeric_line"],
                    "cell_name": row["candidate_name"],
                    "elected": row["elected"],
                }
            )
    profile["candidate_names_recovered_from_wrapped_cells_2016"] = len(name_checks)
    profile["winner_names_recovered_from_wrapped_cells_2016"] = sum(
        row["elected"] for row in name_checks
    )
    with (release / "name_cell_checks.csv").open("w") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "ward_no",
                "candidate_no",
                "source_page",
                "source_row",
                "line_name",
                "cell_name",
                "elected",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(name_checks)
    (release / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    (release / "schema.json").write_text(
        json.dumps({name: descriptor(name) for name in TABLES}, indent=2) + "\n"
    )
    with (release / "dictionary.csv").open("w") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["table", "column", "type", "nullable", "description"])
        for name in TABLES:
            for field in descriptor(name)["fields"]:
                writer.writerow(
                    [
                        name,
                        field["name"],
                        field["arrowType"],
                        not field.get("constraints", {}).get("required", False),
                        field["description"],
                    ]
                )
    (release / "checksums.json").write_text(
        json.dumps(
            {
                p.name: sha(p)
                for p in sorted(release.iterdir())
                if p.name != "checksums.json"
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(profile, indent=2))
    return outputs


if __name__ == "__main__":
    build()
