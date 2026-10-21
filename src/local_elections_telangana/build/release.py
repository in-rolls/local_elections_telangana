"""Verify the published files, run the checks, and write MANIFEST.json.

Every check states what it appeals to. An `external` check compares the data
with a figure published elsewhere and can catch a misread; an `internal` check
only shows the file agrees with itself. Each records `pass`, `warn`, `fail` or
`not_run` with the reason, and `verify` exits non-zero only on a `fail` of a
check marked `blocking` or on a hash mismatch.

Commands:
  verify   recompute hashes, run checks, compare with data/MANIFEST.json
  write    rebuild data/MANIFEST.json and the checks block in data/README.md
"""

import argparse
import csv
import gzip
import hashlib
import json
import re
import subprocess
import sys

import pandas as pd

from local_elections_telangana.build import contract
from local_elections_telangana.build import reference as ref
from local_elections_telangana.parse import y2025_sec
from local_elections_telangana.parse.common import DATA, ROOT, fold

MANIFEST = DATA / "MANIFEST.json"
OUTPUTS = [
    "2019/sarpanch_results.parquet",
    "2019/sarpanch_candidates.parquet",
    "2019/ward_results.parquet",
    "2025/sarpanch_results.parquet",
    "2025/sarpanch_candidates.parquet",
    "2025/ward_results.parquet",
    "2025/eenadu_results.parquet",
    "2025/eenadu_mandal_counts.parquet",
    "2025/eenadu_page_counts.parquet",
]
# 2019 candidate-table district names that changed before the elected listing
# was taken.
RENAMED_2019 = {
    "Warangal Urban": "Hanumakonda",
    "Jayashankar": "Jayashankar Bhupalpally",
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_sha256(path):
    """sha256 of a fetched file as received.

    Large HTML responses are committed gzipped (path + ".gz"); their hash is
    taken on the decompressed bytes, so it still matches the fetch log.
    """
    if path.exists():
        return sha256(path)
    packed = path.with_name(path.name + ".gz")
    if packed.exists():
        return hashlib.sha256(gzip.decompress(packed.read_bytes())).hexdigest()
    # Files over GitHub's 100 MB limit are committed as byte-split parts
    # (`split -b 90m -a 1 FILE FILE.part_`); cat the parts to restore it.
    parts = sorted(path.parent.glob(path.name + ".part_*"))
    if parts:
        digest = hashlib.sha256()
        for part in parts:
            digest.update(part.read_bytes())
        return digest.hexdigest()
    return None


def result(name, appeals_to, status, detail, blocking=False, **numbers):
    return {
        "check": name,
        "appeals_to": appeals_to,
        "status": status,
        "blocking": blocking,
        "detail": detail,
        **numbers,
    }


# ------------------------------------------------------------------- 2019


def checks_2019():
    seats = pd.read_parquet(DATA / "2019/sarpanch_results.parquet")
    cands = pd.read_parquet(DATA / "2019/sarpanch_candidates.parquet")
    out = []
    n = len(seats)
    total = ref.TOTAL_2019["value"]
    out.append(
        result(
            "2019_coverage_vs_notified",
            "external",
            "pass" if 0.90 <= n / total <= 1.0 else "fail",
            f"{n:,} elected sarpanches of {total:,} notified posts "
            f"({n / total:.1%}). Source: {ref.TOTAL_2019['source']}",
            rows=n,
            reference=total,
        )
    )
    key = ["district", "block", "gram_panchayat"]
    dup = seats[seats.duplicated(key, keep=False)].sort_values(key)
    out.append(
        result(
            "2019_key_unique",
            "internal",
            "pass" if dup.empty else "warn",
            f"{dup[key].drop_duplicates().shape[0]} (district, mandal, GP) keys "
            f"appear more than once ({len(dup)} rows). Kept as printed: two GPs "
            "can share a name inside a mandal, and the listing has no GP code.",
            duplicate_keys=dup[key].drop_duplicates().values.tolist(),
        )
    )
    women = seats["reserved_woman"].mean()
    out.append(
        result(
            "2019_women_share_vs_statute",
            "external",
            "pass" if women >= 0.495 else "fail",
            f"{women:.2%} of seats reserved for women; the Act requires 50% "
            "(rounded down where a category's count is odd).",
            share=round(float(women), 4),
        )
    )
    # Two sources that share nothing: the SEC's elected listing and the open
    # data portal's vote counts. The winner should be the top vote-getter.
    c = cands.copy()
    c["district"] = c["district"].replace(RENAMED_2019)
    c["k"] = c["district"].map(fold) + "|" + c["block"].map(fold) + "|"
    c["k"] = c["k"] + c["gram_panchayat"].map(fold)
    top = c.sort_values("candidate_votes", ascending=False).groupby("k").head(2)
    first = top.groupby("k").head(1).set_index("k")
    second = top.groupby("k").nth(1).set_index("k")["candidate_votes"]
    first["tied"] = first["candidate_votes"].eq(second.reindex(first.index))
    s = seats.copy()
    s["k"] = s["district"].map(fold) + "|" + s["block"].map(fold) + "|"
    s["k"] = s["k"] + s["gram_panchayat"].map(fold)
    s = s.drop_duplicates("k", keep=False)
    j = s.join(first[["candidate", "candidate_votes", "tied"]], on="k", how="inner")
    j = j[~j["tied"] & j["candidate_votes"].gt(0)]
    agree = (j["winner"].map(fold) == j["candidate"].map(fold)).mean()
    out.append(
        result(
            "2019_winner_is_top_vote_getter",
            "external",
            "pass" if agree >= 0.95 else "fail",
            f"Of {len(j):,} GPs found in both the SEC elected listing and the "
            f"open-data vote table (untied, votes > 0), the listed winner is the "
            f"top vote-getter in {agree:.1%}. Mismatches include spelling "
            "differences between the two releases.",
            compared=len(j),
            agree=round(float(agree), 4),
        )
    )
    wards = pd.read_parquet(DATA / "2019/ward_results.parquet")
    n = len(wards)
    out.append(
        result(
            "2019_ward_coverage_vs_notified",
            "external",
            "warn",
            f"{n:,} ward members against {ref.WARDS_2019['value']:,} ward seats "
            f"({n / ref.WARDS_2019['value']:.1%}); the listing covers part of the "
            f"state. Source: {ref.WARDS_2019['source']}",
            rows=n,
        )
    )
    key = ["district", "block", "gram_panchayat", "ward_no"]
    dup = wards.duplicated(key, keep=False)
    women = wards["reserved_woman"].mean()
    out.append(
        result(
            "2019_ward_key_and_women_share",
            "internal",
            "pass" if not dup.any() and 0.45 <= women <= 0.55 else "warn",
            f"(district, mandal, GP, ward) repeats on {int(dup.sum())} rows; "
            f"{women:.2%} of wards reserved for women; "
            f"{int(wards['unopposed'].sum()):,} filled unanimously.",
        )
    )
    return out


# ------------------------------------------------------------------- 2025


def sec_district_counts():
    """Per-district GP totals from the SEC phase-wise table's text layer."""
    pdf = DATA / "raw/2025/sec/sec_phasewise_gp_elections_2025.pdf"
    text = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    counts = {}
    for line in text.splitlines():
        got = re.match(r"^\s*\d+\s+([A-Za-z][A-Za-z .]+?)\s{2,}([\d\s]+)$", line)
        if not got:
            continue
        nums = [int(x) for x in got.group(2).split()]
        if len(nums) != 13:
            continue
        name = ref.SEC_TABLE_NAMES.get(got.group(1).strip(), got.group(1).strip())
        # columns: divisions, then (divisions, mandals, GPs, wards) per phase
        counts[name] = nums[3] + nums[7] + nums[11]
    return counts


def checks_2025():
    """The commission's own 2025 tables: two reports and published totals."""
    seats = pd.read_parquet(DATA / "2025/sarpanch_results.parquet")
    cands = pd.read_parquet(DATA / "2025/sarpanch_candidates.parquet")
    out = []

    problems = {name: contract.failures(name) for name in contract.TABLES}
    bad = {k: v for k, v in problems.items() if v}
    out.append(
        result(
            "2025_table_schema",
            "internal",
            "fail" if bad else "pass",
            "Each 2025 table matches its Table Schema in data/schemas/ (Arrow "
            f"types, required fields, codes, keys). Failing: {bad or 'none'}.",
            blocking=True,
        )
    )

    # The district report and the mandal reports are separate queries of the
    # same results; a mandal the collector missed shows up as a shortfall.
    counts = y2025_sec.district_report_counts()
    rows = []
    for (kind, d), whole in sorted(counts.items()):
        col = "result_declared" if kind == "E" else "a_path"
        part = seats[seats["district_id"].eq(d) & seats[col].notna()]
        if kind == "E":
            part = part[part["result_declared"]]
        # the E report's repeats are counted in the district report too
        twice = int(part["listed_twice"].sum()) if kind == "E" else 0
        rows.append(
            {
                "report": kind,
                "district_id": d,
                "district": whole,
                "mandals": len(part) + twice,
                "diff": len(part) + twice - whole,
            }
        )
    table = pd.DataFrame(rows)
    off = table[table["diff"] != 0]
    out.append(
        result(
            "2025_mandal_reports_vs_district_reports",
            "internal",
            "pass" if off.empty else "warn",
            f"GPs in the mandal reports against the district reports, per "
            f"district and report: {len(off)} of {len(table)} differ "
            f"(mandal total {int(table['mandals'].sum()):,}, district total "
            f"{int(table['district'].sum()):,}).",
            differences=off.to_dict("records"),
        )
    )

    both = seats[seats["in_reports"].eq("both")]
    only = (
        seats["in_reports"]
        .value_counts()
        .reindex(["elected_only", "candidates_only"], fill_value=0)
    )
    same = both["winner"].map(fold) == both["elected_name"].map(fold)
    out.append(
        result(
            "2025_elected_report_vs_candidates_report",
            "internal",
            "pass" if same.mean() >= 0.99 else "warn",
            f"Of {len(both):,} GPs in both mandal reports, the E report's winner "
            f"is the A report's 'Elected' candidate in {same.mean():.2%}. "
            f"Only in E: {only['elected_only']}; only in A: "
            f"{only['candidates_only']}.",
            mismatches=both.loc[
                ~same, ["district", "block", "gram_panchayat", "winner", "elected_name"]
            ].to_dict("records"),
        )
    )
    res_same = both["reserved_raw"] == both["reserved_raw_a"]
    out.append(
        result(
            "2025_reservation_same_in_both_reports",
            "internal",
            "pass" if res_same.all() else "fail",
            f"Reservation code agrees between the E and A reports for "
            f"{int(res_same.sum()):,} of {len(both):,} GPs.",
            blocking=True,
        )
    )

    c = cands.merge(
        seats[["a_path", "a_locator", "total_valid_votes"]].dropna(),
        left_on=["source_path", cands["source_locator"].str.split(",").str[0]],
        right_on=["a_path", "a_locator"],
    )
    sums = c.groupby(["a_path", "a_locator"]).agg(
        votes=("candidate_votes", "sum"), valid=("total_valid_votes", "first")
    )
    adds = (sums["votes"] == sums["valid"]).mean()
    top = c.sort_values("candidate_votes", ascending=False).groupby(
        ["a_path", "a_locator"]
    )
    first, second = top.nth(0), top.nth(1)
    first = first.set_index(["a_path", "a_locator"])
    second = second.set_index(["a_path", "a_locator"])["candidate_votes"]
    contested = first[first["total_valid_votes"].gt(0)]
    untied = contested[contested["candidate_votes"] > second.reindex(contested.index)]
    top_elected = untied["elected"].mean()
    out.append(
        result(
            "2025_elected_is_top_vote_getter",
            "internal",
            "pass" if top_elected >= 0.99 and adds >= 0.99 else "warn",
            f"In {len(untied):,} contested GPs without a tie for first, the "
            f"candidate marked Elected has the most votes in {top_elected:.2%}. "
            f"Candidates' votes add up to the caption's valid votes in "
            f"{adds:.2%} of {len(sums):,} GPs.",
        )
    )

    key = ["district_id", "mandal_id", "gram_panchayat"]
    dup = seats[seats.duplicated(key, keep=False)].sort_values(key)
    out.append(
        result(
            "2025_key_unique",
            "internal",
            "pass" if dup.empty else "warn",
            f"{dup[key].drop_duplicates().shape[0]} (district, mandal, GP) names "
            f"appear more than once ({len(dup)} rows). GPs without a GP code: "
            f"{int(seats['gp_code'].isna().sum())}. GPs the E report prints twice "
            f"(repeat dropped): {int(seats['listed_twice'].sum())}.",
            duplicate_rows=dup[[*key, "winner"]].to_dict("records"),
        )
    )

    sec = sec_district_counts()
    got = seats.groupby("district").size()
    rows = []
    for d, official in sorted(sec.items()):
        rows.append(
            {
                "district": d,
                "sec_table": official,
                "seats": int(got.get(d, 0)),
                "diff": int(got.get(d, 0)) - official,
            }
        )
    table = pd.DataFrame(rows)
    unmatched = sorted(set(got.index) - set(sec))
    off = table[table["diff"].abs() > table["sec_table"] * 0.01]
    out.append(
        result(
            "2025_district_counts_vs_sec_phase_table",
            "external",
            "pass" if off.empty and not unmatched else "warn",
            f"GPs per district against the SEC's September phase table "
            f"({sum(sec.values()):,} GPs): {len(off)} district(s) differ by more "
            f"than 1%. Districts not in the table: {unmatched or 'none'}. "
            f"Total {len(seats):,}.",
            by_district=table.to_dict("records"),
        )
    )
    n = len(seats)
    posts = ref.TOTALS_2025["sarpanch_posts_notified"]["value"]
    out.append(
        result(
            "2025_coverage_vs_notified",
            "external",
            "pass" if abs(n / posts - 1) <= 0.01 else "warn",
            f"{n:,} GPs against {posts:,} sarpanch posts notified "
            f"({n / posts:.2%}; the SEC's GP count is "
            f"{ref.TOTALS_2025['gps_notified']['value']:,}); with a declared winner: "
            f"{int(seats['result_declared'].sum()):,}.",
            rows=n,
        )
    )

    # GO 46 reserves half of each category's seats for women, rounded down.
    # The data show the rounding happens within each mandal and category,
    # which is why the statewide share is below 50%.
    women = seats["reserved_woman"].mean()
    cells = seats.groupby(["district_id", "mandal_id", "reserved_caste"])[
        "reserved_woman"
    ].agg(["sum", "size"])
    floor = cells["sum"].eq(cells["size"] // 2)
    bc = int(seats["reserved_caste"].eq("BC").sum())
    out.append(
        result(
            "2025_women_and_category_shares",
            "external",
            "pass" if floor.mean() >= 0.95 else "warn",
            f"Women's seats equal half the seats, rounded down, in "
            f"{floor.mean():.1%} of {len(cells):,} mandal x category groups; "
            f"statewide {women:.2%} of seats are reserved for women. BC seats "
            f"{bc:,} of {n:,} ({bc / n:.2%}) against the SEC's reported "
            f"{ref.BC_2025['seats']:,} of {ref.BC_2025['of']:,} "
            f"({ref.BC_2025['share']:.2%}; {ref.BC_2025['source']}). Rule: "
            f"{ref.WOMEN_STATUTE['source']}",
            women_share=round(float(women), 4),
            floor_rule_share=round(float(floor.mean()), 4),
            off_rule=cells[~floor].reset_index().to_dict("records"),
            bc_seats=bc,
        )
    )

    e = pd.read_parquet(DATA / "2025/eenadu_results.parquet")
    ours = seats.groupby("district").size()
    theirs = e.groupby("district").size()
    gap = (ours - theirs.reindex(ours.index)).dropna().astype(int)
    out.append(
        result(
            "2025_district_counts_vs_eenadu",
            "external",
            "pass" if gap.abs().max() <= 0.01 * ours.max() else "warn",
            f"GPs per district, SEC minus Eenadu's newspaper tables (independent "
            f"source): {int((gap != 0).sum())} of {len(gap)} districts differ; "
            f"largest gap {int(gap.abs().max())}. Totals: SEC {len(seats):,}, "
            f"Eenadu {len(e):,}.",
            by_district=gap[gap != 0].to_dict(),
        )
    )
    return out


def checks_eenadu():
    seats = pd.read_parquet(DATA / "2025/eenadu_results.parquet")
    pages = pd.read_parquet(DATA / "2025/eenadu_page_counts.parquet")
    out = []
    n = len(seats)
    sec = sec_district_counts()
    if (
        len(sec) != 31
        or sum(sec.values()) != ref.TOTALS_2025["sec_phase_table_gps"]["value"]
    ):
        raise SystemExit(
            f"SEC table read wrongly: {len(sec)} districts, {sum(sec.values())}"
        )
    got = seats.groupby("district").size()
    rows = []
    for d, official in sorted(sec.items()):
        held = ref.COURT_HELD_2025.get(d, 0)
        rows.append(
            {
                "district": d,
                "sec_table": official,
                "court_held": held,
                "eenadu_rows": int(got.get(d, 0)),
                "diff": int(got.get(d, 0)) - official,
            }
        )
    table = pd.DataFrame(rows)
    worst = table["diff"].abs().max()
    off = table[table["diff"].abs() > table["sec_table"] * 0.01]
    out.append(
        result(
            "eenadu_district_counts_vs_sec",
            "external",
            "pass" if off.empty else "warn",
            f"Eenadu rows per district against the SEC phase table (31 districts, "
            f"{sum(sec.values()):,} GPs). {len(off)} district(s) differ by more "
            f"than 1%; largest absolute gap {worst}. Total rows {n:,}.",
            blocking=False,
            by_district=table.to_dict("records"),
        )
    )
    refs = {k: v["value"] for k, v in ref.TOTALS_2025.items()}
    out.append(
        result(
            "eenadu_coverage_vs_notified",
            "external",
            "pass" if 0.98 <= n / refs["sarpanch_posts_notified"] <= 1.0 else "warn",
            f"{n:,} GP rows against {refs['sarpanch_posts_notified']:,} sarpanch "
            f"posts notified ({n / refs['sarpanch_posts_notified']:.2%}). Other "
            f"published denominators: {refs}.",
            rows=n,
        )
    )
    pend = pages[pages["declared"] != pages["total"]]
    out.append(
        result(
            "eenadu_pages_internally_complete",
            "internal",
            "pass" if (pages["rows"] == pages["total"]).all() else "warn",
            f"Every page's row count equals its printed panchayat total: "
            f"{bool((pages['rows'] == pages['total']).all())}. Pages whose "
            f"printed declared count is below their total: {len(pend)}.",
        )
    )
    key = ["district", "block", "gram_panchayat"]
    dup = seats[seats.duplicated(key, keep=False)].sort_values(key)
    out.append(
        result(
            "eenadu_key_unique",
            "internal",
            "pass" if dup.empty else "warn",
            f"{dup[key].drop_duplicates().shape[0]} (district, mandal, GP) keys "
            f"appear more than once ({len(dup)} rows).",
            duplicate_rows=dup[[*key, "winner", "source_locator"]].to_dict("records"),
        )
    )
    declared = seats[seats["result_declared"]]
    counts = (
        declared["backing_party"]
        .where(declared["backing_party"].isin(["INC", "BRS", "BJP"]), "OTH")
        .value_counts()
    )
    theirs = ref.PARTY_2025["counts"]
    tot_t, tot_o = sum(theirs.values()), int(counts.sum())
    gaps = {
        p: round(float(counts.get(p, 0) / tot_o - theirs[p] / tot_t), 4) for p in theirs
    }
    out.append(
        result(
            "eenadu_backing_party_vs_siasat",
            "external",
            "pass" if max(abs(g) for g in gaps.values()) <= 0.02 else "warn",
            f"Share of GPs by backing party, Eenadu minus Siasat: {gaps}. "
            f"Eenadu counts {counts.to_dict()} of {tot_o:,}; Siasat {theirs} of "
            f"{tot_t:,} (declared results only). Both are newspaper tallies, "
            f"so agreement shows the parse is faithful, not that either is official. "
            f"{ref.PARTY_2025['source']}",
            share_gap=gaps,
        )
    )
    return out


# District groups that stay comparable across the 2019 and 2021 reorganisations.
GROUP = {
    "Bhadradri": "Bhadradri Kothagudem",
    "Komaram Bheem": "Komaram Bheem Asifabad",
    "Yadadri Bhongiri": "Yadadri Bhuvanagiri",
    "Mulugu": "Jayashankar Bhupalpally",
    "Narayanpet": "Mahabubnagar",
    "Warangal Rural": "Warangal+Hanumakonda",
    "Warangal": "Warangal+Hanumakonda",
    "Hanumakonda": "Warangal+Hanumakonda",
}


def group(district):
    return GROUP.get(district, district)


def loose(text):
    """Collapse what English spellings of Telugu names vary on.

    Vowel length, aspiration, retroflex vs dental, v/w, s/sh, doubled letters.
    """
    t = fold(text)
    for a, b in [
        ("aa", "a"),
        ("ee", "i"),
        ("oo", "u"),
        ("ii", "i"),
        ("uu", "u"),
        ("th", "t"),
        ("dh", "d"),
        ("bh", "b"),
        ("kh", "k"),
        ("gh", "g"),
        ("ph", "p"),
        ("ch", "c"),
        ("sh", "s"),
        ("w", "v"),
        ("z", "j"),
        ("y", "i"),
        ("e", "i"),
        ("o", "u"),
    ]:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)
    return re.sub(r"(m|n)(?=[kgcjtdpb])", "n", t)


def link_preview():
    """Share of 2025 GPs whose name matches a 2019 GP in the same district group.

    A preview for the 2019 -> 2025 link, not the link itself: names only, no
    mandal, no one-to-one assignment.
    """
    s19 = pd.read_parquet(DATA / "2019/sarpanch_results.parquet")
    s25 = pd.read_parquet(DATA / "2025/sarpanch_results.parquet")
    s19 = s19.assign(district=s19["district"].map(group))
    s25 = s25.assign(district=s25["district"].map(group))
    exact19 = set(zip(s19["district"], s19["gram_panchayat"].map(fold), strict=True))
    loose19 = set(zip(s19["district"], s19["gram_panchayat"].map(loose), strict=True))
    pairs = list(zip(s25["district"], s25["gram_panchayat"], strict=True))
    exact = sum((d, fold(g)) in exact19 for d, g in pairs)
    near = sum((d, loose(g)) in loose19 for d, g in pairs)
    # Chance benchmark: the same rule against the next district group's 2019
    # names, which share no GPs by design.
    groups = sorted(set(s19["district"]))
    shift = dict(zip(groups, groups[1:] + groups[:1], strict=True))
    chance = sum((shift.get(d, d), loose(g)) in loose19 for d, g in pairs)
    n = len(pairs)
    unmatched = sorted(set(s19["district"]) ^ set(s25["district"]))
    return result(
        "link_preview_2019_2025",
        "internal",
        "info",
        f"2025 GP names found among 2019 GP names of the same district group: "
        f"exact (folded) {exact / n:.1%}; loose (vowel length, aspiration, v/w, "
        f"s/sh collapsed) {near / n:.1%}; loose against a different district's "
        f"names (chance benchmark) {chance / n:.1%}. District groups absorb the "
        f"2019 and 2021 reorganisations. Groups in one year only: {unmatched}.",
        exact_within_district=round(exact / n, 4),
        loose_within_district=round(near / n, 4),
        loose_other_district=round(chance / n, 4),
    )


# ------------------------------------------------------------- manifest


def schema(path):
    import pyarrow.parquet as pq

    s = pq.read_schema(path)
    return [{"name": f.name, "type": str(f.type)} for f in s]


def files_entry():
    entries = []
    for rel in OUTPUTS:
        path = DATA / rel
        entries.append(
            {
                "file": rel,
                "sha256": sha256(path),
                "rows": len(pd.read_parquet(path)),
                "schema": schema(path),
            }
        )
    return entries


def raw_entries():
    log = ROOT / "data/raw/fetch_log.csv"
    with log.open(encoding="utf-8") as fh:
        fetched = list(csv.DictReader(fh))
    # Files held rather than fetched: copied from in-rolls/local_elections,
    # where they were committed without a fetch record.
    logged = {row["path"] for row in fetched}
    held = [
        {"path": str(p.relative_to(ROOT)), "sha256": sha256(p)}
        for folder in ("raw/2019", "raw/urban", "raw/docs")
        for p in sorted((DATA / folder).rglob("*"))
        if p.is_file() and str(p.relative_to(ROOT)) not in logged
    ]
    return fetched, held


def check_sources_exist():
    """Every seat's source_path names a committed file, as written."""
    tables = [
        "2019/sarpanch_results.parquet",
        "2019/ward_results.parquet",
        "2025/sarpanch_results.parquet",
        "2025/ward_results.parquet",
    ]
    paths = set()
    for table in tables:
        paths |= set(pd.read_parquet(DATA / table, columns=["source_path"]).source_path)
    missing = sorted(p for p in paths if not (DATA.parent / p).exists())
    return result(
        "source_paths_exist",
        "internal",
        "fail" if missing else "pass",
        "every source_path in the seat tables is a file in the repository",
        blocking=True,
        paths=len(paths),
        missing=len(missing),
        examples=missing[:3],
    )


def run_checks():
    return (
        checks_2019()
        + checks_2025()
        + checks_eenadu()
        + [check_sources_exist(), link_preview()]
    )


def verify():
    manifest = json.loads(MANIFEST.read_text())
    problems = []
    for entry in manifest["outputs"]:
        if sha256(DATA / entry["file"]) != entry["sha256"]:
            problems.append(f"hash changed: {entry['file']}")
    fetched, _ = raw_entries()
    for row in fetched:
        if raw_sha256(ROOT / row["path"]) != row["sha256"]:
            problems.append(f"raw file missing or changed since fetch: {row['path']}")
    for row in manifest["raw_held"]:
        if sha256(ROOT / row["path"]) != row["sha256"]:
            problems.append(f"raw file changed: {row['path']}")
    checks = run_checks()
    blocking = [c["check"] for c in checks if c["blocking"] and c["status"] == "fail"]
    stale = [
        c["check"]
        for c, m in zip(checks, manifest["checks"], strict=False)
        if c["status"] != m["status"]
    ]
    for c in checks:
        print(f"  {c['status']:8} {c['check']}")
    if stale:
        problems.append(f"check status differs from MANIFEST.json: {stale}")
    if blocking:
        problems.append(f"blocking checks failed: {blocking}")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        raise SystemExit(1)


def write():
    fetched, held = raw_entries()
    checks = run_checks()
    manifest = {
        "format_version": 1,
        "outputs": files_entry(),
        "raw_fetched": fetched,
        "raw_held": held,
        "checks": checks,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    lines = ["<!-- checks:start -->", "", "| Check | Appeals to | Status | Result |"]
    lines.append("| --- | --- | --- | --- |")
    for c in checks:
        detail = c["detail"].replace("|", "/")
        lines.append(
            f"| `{c['check']}` | {c['appeals_to']} | {c['status']} | {detail} |"
        )
    lines.extend(["", "<!-- checks:end -->"])
    readme = DATA / "README.md"
    text = readme.read_text()
    pattern = r"<!-- checks:start -->.*?<!-- checks:end -->"
    readme.write_text(re.sub(pattern, lambda _: "\n".join(lines), text, flags=re.S))
    for c in checks:
        print(f"  {c['status']:8} {c['check']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify", "write"])
    args = parser.parse_args()
    verify() if args.command == "verify" else write()


if __name__ == "__main__":
    main()
