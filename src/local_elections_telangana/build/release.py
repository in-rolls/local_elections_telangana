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
import hashlib
import json
import re
import subprocess
import sys
import unicodedata

import pandas as pd

from local_elections_telangana.build import reference as ref
from local_elections_telangana.parse.common import DATA, ROOT, fold

MANIFEST = DATA / "MANIFEST.json"
OUTPUTS = [
    "2019/sarpanch_results.parquet",
    "2019/sarpanch_candidates.parquet",
    "2025/sarpanch_results.parquet",
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
    women = seats["woman_reserved"].mean()
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
    seats = pd.read_parquet(DATA / "2025/sarpanch_results.parquet")
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
            "2025_district_counts_vs_sec",
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
            "2025_coverage_vs_notified",
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
            "2025_pages_internally_complete",
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
            "2025_key_unique",
            "internal",
            "pass" if dup.empty else "warn",
            f"{dup[key].drop_duplicates().shape[0]} (district, mandal, GP) keys "
            f"appear more than once ({len(dup)} rows).",
            duplicate_rows=dup[[*key, "winner", "source_locator"]].to_dict("records"),
        )
    )
    out.append(
        result(
            "2025_women_and_category_shares",
            "external",
            "not_run",
            "No 2025 reservation source is parsed: Eenadu prints none, the "
            "commission's tables need an Indian connection, and the collectorate "
            "statements found are scans. Reference figures to use once it is: "
            f"BC {ref.BC_2025['seats']:,} of {ref.BC_2025['of']:,} "
            f"({ref.BC_2025['share']:.2%}; {ref.BC_2025['source']}); women "
            f"{ref.WOMEN_STATUTE['share']:.0%} ({ref.WOMEN_STATUTE['source']}).",
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
            "2025_backing_party_vs_siasat",
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


def link_preview():
    """Share of 2025 GPs whose name matches a 2019 GP after transliteration."""
    try:
        from indic_transliteration import sanscript
    except ImportError:
        return result(
            "link_preview_2019_2025",
            "internal",
            "not_run",
            "indic-transliteration not installed (uv sync --all-groups).",
        )
    s19 = pd.read_parquet(DATA / "2019/sarpanch_results.parquet")
    s25 = pd.read_parquet(DATA / "2025/sarpanch_results.parquet")

    def latin(text):
        # HK marks Telugu's short e/o as è/ò; drop the accent, keep the vowel.
        hk = sanscript.transliterate(text, sanscript.TELUGU, sanscript.HK)
        bare = unicodedata.normalize("NFKD", hk)
        return "".join(c for c in bare if not unicodedata.combining(c))

    def loose(text):
        # Collapse the distinctions English spellings of Telugu names drop:
        # vowel length, aspiration, retroflex vs dental, v/w, s/sh.
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

    d25 = s25.assign(
        exact=s25["gram_panchayat"].map(latin).map(fold),
        lo=s25["gram_panchayat"].map(latin).map(loose),
    )
    s19 = s19.assign(district=s19["district"].map(group))
    d25 = d25.assign(district=d25["district"].map(group))
    n19 = set(zip(s19["district"], s19["gram_panchayat"].map(fold), strict=True))
    l19 = set(zip(s19["district"], s19["gram_panchayat"].map(loose), strict=True))
    l_any = set(s19["gram_panchayat"].map(loose))
    exact = sum(
        (d, g) in n19 for d, g in zip(d25["district"], d25["exact"], strict=True)
    )
    loose_d = sum(
        (d, g) in l19 for d, g in zip(d25["district"], d25["lo"], strict=True)
    )
    loose_s = d25["lo"].isin(l_any).sum()
    # Chance benchmark: the same rule against the 2019 names of the next
    # district group in alphabetical order, which shares no GPs by design.
    groups = sorted(set(s19["district"]))
    shift = dict(zip(groups, groups[1:] + groups[:1], strict=True))
    chance = sum(
        (shift.get(d, d), g) in l19
        for d, g in zip(d25["district"], d25["lo"], strict=True)
    )
    n = len(d25)
    d19 = set(s19["district"])
    d25s = set(d25["district"])
    return result(
        "link_preview_2019_2025",
        "internal",
        "info",
        f"2025 names are Telugu, 2019 names Latin, so a raw exact match is 0 by "
        f"construction. After rule-based Telugu->Latin transliteration "
        f"(indic-transliteration, HK scheme): exact folded match within the same "
        f"district name {exact / n:.1%}; loose match (vowel length, aspiration, "
        f"v/w, s/sh collapsed) within district {loose_d / n:.1%}; loose match "
        f"anywhere in the state {loose_s / n:.1%}; loose match against a "
        f"different district's 2019 names (chance benchmark) {chance / n:.1%}. "
        f"Districts are compared as "
        f"groups that absorb renames and splits (Mulugu and Narayanpet were "
        f"carved out in Feb 2019 and the 2019 listing files them under their "
        f"parents; Hanumakonda and Warangal swapped mandals in 2021). Mandals "
        f"are not used: 2025 mandal names are Telugu and several mandals were "
        f"created after 2019. Unmatched district groups: {sorted(d19 ^ d25s)}.",
        exact_within_district=round(exact / n, 4),
        loose_within_district=round(loose_d / n, 4),
        loose_statewide=round(float(loose_s / n), 4),
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
    held = [
        {"path": f"data/raw/2019/{p.name}", "sha256": sha256(p)}
        for p in sorted((DATA / "raw/2019").glob("*.csv"))
    ]
    return fetched, held


def run_checks():
    return checks_2019() + checks_2025() + [link_preview()]


def verify():
    manifest = json.loads(MANIFEST.read_text())
    problems = []
    for entry in manifest["outputs"]:
        if sha256(DATA / entry["file"]) != entry["sha256"]:
            problems.append(f"hash changed: {entry['file']}")
    fetched, _ = raw_entries()
    for row in fetched:
        if sha256(ROOT / row["path"]) != row["sha256"]:
            problems.append(f"raw file changed since fetch: {row['path']}")
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
