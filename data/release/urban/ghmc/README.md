# GHMC ward elections, 2016 and 2020

This supplement supplies actual candidate and winner records for Greater Hyderabad Municipal Corporation. It concerns ward councilors, not the mayor. New PDF copies were collected November 9, 2026; the official report and winner table were already held upstream and are read in place. No effects are estimated.

| Output in `data/release/urban/ghmc/` | Rows | Coverage |
|---|---:|---|
| `candidates_2016.parquet` | 1,333 | All 150 wards; candidate names, parties, votes, winner indicators and reservation |
| `winners.parquet` | 300 | All 150 winners in each election; explicit sex for 2020 only |
| `candidate_profiles_2020.parquet` | 1,122 | All 150 wards; explicit sex, age, education, occupation and candidate social category |
| `candidate_returns_2020.parquet` | 1,117 | 149 wards; votes and winner indicators; Neredmet (136) absent |

The 2020 profile reports 582 male and 540 female candidates. The official winner list records 81 women and 69 men; 75 wards are women-reserved. All 150 winner sex values are separately printed, including the six women elected in nonquota wards. Sex is never inferred from reservation or names. **All 2016 sex values remain null.** The 2020 profile itself does not declare election outcomes, so its `elected` is null, not false.

## Sources and receipts

- The [2016 result PDF](https://www.myghmc.com/assets/GHMCResult2016.pdf), 52 pages, is a publicly hosted result-table copy, not a newly certified SEC download. Its 1,333 candidate rows and 150 printed `Winner` labels are preserved. Its party totals and ward-level vote sums can be inspected from the output; hosting alone is not treated as independent certification.
- The [2020 candidate-return PDF](https://newsmeter.in/pdf_upload/pdf_upload-288883.pdf), 43 pages, reproduces Proforma XVI on a news outlet's server. Its 149 elected rows exclude Neredmet. All five Neredmet candidates remain available in the separate complete candidate-profile file; their missing votes are not filled with zero.
- The [official candidate-profile PDF](https://tsec.gov.in/pdf/proforma-5GHMC.pdf), 59 pages, was recovered from the [November 29, 2020 archive capture](https://web.archive.org/web/20201129111559id_/https://tsec.gov.in/pdf/proforma-5GHMC.pdf). The report is dated November 26, 2020 and is Proforma V, final contesting candidates. The exact-URL CDX response is retained. Direct TSEC access timed out; the standard Python `wayback` client retrieved the capture.
- The official elected-member table is retained at `data/raw/tsec_docs/files/StatisticalRep/MC/2024/elected_ward_members_of_ghmc,2020_2053.pdf` (seven pages). It explicitly identifies the December 1, 2020 election and prints name, ward, reservation, sex and party. The 2020 election report also reproduces an elected-member table beginning on physical page 793. The separate official winner table preserves Akula Ramesh Goud as the original Lingojiguda winner, rather than substituting a later officeholder.
- The full official election report remains at `data/raw/tsec_docs/files/StatisticalRep/ElectionReport/2021/Election_Report-GHMC-2020-Final-Madhavi_1639.pdf`. It contains the original reservation and boundary orders; no duplicate PDF or extracted-page copies were created in the repository.

`data/raw/fetch_log.csv` records each acquired original's URL, retrieval time, byte count and SHA-256 hash. Existing official-file receipts are preserved. `profile.json` records source hashes and coverage; `checksums.json` records generated-file hashes. `schema.json` contains generated copies of the four table contracts in `schemas/`, and `dictionary.csv` defines their fields. These metadata and `name_cell_checks.csv` sit beside the Parquet files in this directory. Originals remain in `data/raw/urban/ghmc/` or the preexisting TSEC archive.

## Published contracts

The candidate tables use `candidate_name`, `candidate_woman_raw`, `candidate_woman`, `candidate_age`, `candidate_education`, `candidate_caste` and `elected`. The winner table uses `winner`, `winner_woman_raw` and `winner_woman`. All `*_woman` fields are nullable Arrow Int8 values 0/1/null. Ward and candidate identifiers are strings (`ward_no`, `candidate_no`); year remains an integer, and `body` identifies GHMC. `reserved_caste=NONE` means no caste restriction. Original category labels remain in `reserved_raw` and `candidate_caste_raw`.

These are source-specific tables, not fabricated pooled records: no district, commit identifier or synthetic pooled row identifier has been added. Keys are `(year, body, ward_no, candidate_no)` for candidate tables and `(year, body, ward_no)` for winners. Exact Arrow types, nullability, enums and required fields are enforced by the repository's existing contract verifier. All four tables are included in `data/MANIFEST.json`; `make check` also verifies coverage, source hashes, recorded-sex consistency and that unreported outcomes remain null. `renames.csv` records the code, path, column and type changes; original PDFs are unchanged.

## Handling and joins

The left-hand universe for the result-return handoff is the 1,117 printed candidate rows. These form 149 blocks, each beginning with candidate number 1. Ward cells spanning page breaks sometimes lose their number in ordinary PDF table extraction, and the first `S.No` column is an enumeration rather than the ward ID: it shifts after omitted ward 136. Forward-filling either extracted labels or that serial can silently misassign candidates.

The parser therefore identifies each candidate block's ward from the complete official profile roster. It removes punctuation and whitespace and folds case in candidate names solely for linkage, then intersects the possible profile wards for the block's matching names. Every block must identify exactly one ward; ambiguous blocks fail. All 149 blocks identify distinct wards, and every directly extractable printed ward number must agree. The resulting 1,117 `(ward_no, candidate_no)` keys are unique. This is documented within-election record linkage, not an assumption about geographic continuity. Raw cells, original names, page/row references, `ward_label_cell_raw`, `ward_source_path` and `ward_link_basis` preserve the evidence. Profile and return candidate numbers are source-specific and should not be assumed interchangeable when joining individual candidates.

Because some return reservation cells overlap page headers, its adopted ward name and reservation come from the complete official elected-member table. `reserved_source_path` identifies this source; `raw_record` preserves the return's original cells. No winner sex or candidate education is silently transferred between sources. The 2016 file requires all 1,333 candidates, all 150 wards and exactly one winner per ward. Numeric result lines supply votes and status; complete PDF name cells supply names. The earlier line parser missed 29 names wrapped above and below the numeric line, including four winners. Reading the name cells restores all 29; `name_cell_checks.csv` records these changes. Representative original pages 8 and 29 were visually checked. Each 2016 `raw_record` retains the exact original numeric line, full extracted name cell, its bounding box, and the old line-based name reading. The 2020 winner parser follows printed row boundaries and checks ward/serial agreement; it excludes the commissioner-signature footer from the last winner's name.

Raw education labels, including `--`, are preserved rather than converted to an unsupported credential scale. Null means that the adopted source does not supply the field or the printed value could not be represented by its type. The data are source supplements, not a fully reconciled candidate panel. No 2009 candidate file or 2009–2016 geographic crosswalk was acquired in this pass.

## Reservation histories and geographic evidence

The retained report contains **G.O.Rt.No.562, October 31, 2020**, physical PDF page 148 / printed page 136, retaining the 2016 ward reservations for the 2020 election as the second term. **G.O.Rt.No.561 of the same date**, physical page 155 / printed page 143, retains the delimitation finalized for the 2016 election. Both original orders were visually inspected. G.O.Ms.No.25, January 8, 2016, follows on physical pages 149–150; the 2020 ward reservation table is on physical pages 156–159.

The 2016 result-table categories and official 2020 winner-table categories agree for all 150 wards, including the 75 women-reserved wards. Thus **2016–2020 contains no quota exits** and cannot supply the paper's post-quota persistence contrast. The retained orders support boundary continuity for this pair; they do not establish continuity with 2009 or any later reorganization. Current-quota characteristics and repeated-reservation outcomes are separate questions.

## Reproduction

From the repository root, with project dependencies installed:

```sh
PYTHONPATH=src python -m local_elections_telangana.collect.ghmc
PYTHONPATH=src python -m local_elections_telangana.parse.ghmc
PYTHONPATH=src python -m pytest -q tests/test_ghmc.py
make manifest
make check
```

Collection is explicit and skips only retained files with matching receipts. Parsing is offline and verifies source hashes before extraction. The source report and this supplement do not modify the established rural releases.
