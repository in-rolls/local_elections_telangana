# Data

## Sources

### 2019

| File | What | Origin |
|---|---|---|
| `raw/2019/2019_gp_sarpanch.csv` | 12,018 elected sarpanches with seat reservation codes (`UR/SC/ST/BC` × `(G)` general / `(W)` woman) | The columns are exactly those of the SEC's "Know your PR representative – Rural" report, `https://tsec.gov.in/knowPRRural.do` ("Only Elected Candidates"), with a District column added. Committed to in-rolls/local_elections on 2023-06-10, with no URL recorded. The URL is **inferred** from the column match and the post-2021 district names (Hanumakonda). |
| `raw/2019/grampanchayatelectionsdata_2019_sarpanch.csv` | 35,121 candidate rows: votes per candidate, plus valid, rejected and tendered votes and NOTA per GP, with SEC district/mandal/GP codes | Telangana Open Data Portal, `https://data.telangana.gov.in/dataset/telangana-gram-panchayat-sarpanch-election-data-2019` (recorded in local_elections' 2022 readme; the portal does not answer from outside India). |

Both files were copied unchanged from `local_elections/data/telangana/raw/`.
`raw_held` in MANIFEST.json gives their hashes.

Also from in-rolls/local_elections (held there until commit `a89a170`, now
here; hashes in MANIFEST.json `raw_held`):

| File | What |
|---|---|
| `raw/2019/ward/2019_ward_<district>.csv` | 49,823 elected ward members in 30 district files, misaligned against their own header (see `parse/y2019.py`); parsed into `2019/ward_results.parquet` |
| `raw/urban/municipal_2020.csv`, `municipal_2021_bye_elections.csv` | 2020 municipal ward results and 2021 by-elections, every candidate's votes; not parsed here (urban bodies) |
| `raw/urban/*.pdf` | 2020 mayor/chairperson reservation G.O.s 7 & 8 and 2021 ULB ward reservations |
| `raw/docs/*.pdf` | the SEC's 2022 manual of election law and the 2001 report `NN-II-2001-FINAL.pdf` |

### 2025

| Files | What | Origin |
|---|---|---|
| `raw/2025/sec/sec_notification_1085_2025-11-25_{english,telugu}.pdf` | SEC Notification 1085/TGSEC-PR/2025 calling the December election. It names 32 GPs held back by court orders (Mulugu 25, Karimnagar 2, Khammam 5). Annexure-II (counts by phase) is missing from the uploaded scan | tsec.gov.in via Internet Archive captures (`web.archive.org/web/<ts>id_/…`) |
| `raw/2025/sec/sec_phasewise_gp_elections_2025.pdf` | SEC phase-wise GP counts per district, 31 districts, 12,733 GPs (September 2025 schedule; the election was re-notified in November with new phases) | same |
| `raw/2025/tsec/report_{E,A}/district_<d>.html.gz`, `.../by_mandal/district_<d>_<m>.html.gz` | The SEC's own results, per district and per mandal: E ("Only Elected Candidates": GP, reservation code, winner) and A ("All Contested Candidates": per GP the reservation, valid/rejected/tendered/NOTA votes, and every candidate's votes and result). 33 districts and every mandal | `https://tsec.gov.in/knowPRRural.se` (POST), collected 2026-10-18 and 2026-10-19 through a Mumbai VM by `collect/tsec.py` |
| `raw/2025/tsec/frame/mandals_<d>.html.gz`, `gps_<d>_<m>.html.gz` | The form's mandal and GP dropdowns: the SEC's mandal and GP codes | same form, `getMandal` / `getGramPanchayat` |
| `raw/2025/eenadu/phase{1,2,3}/<district>.html` | Eenadu's results tables: per district and phase, a block per mandal, a row per GP: panchayat, winner, backing party | `https://www.eenadu.net/telangana/panchayat-elections-results-phase{p}/{district}` |

`raw/fetch_log.csv` records the URL, sha256, size, HTTP status and UTC fetch
time of every fetched file. The fetcher skips anything already logged.

**The SEC's tables are the 2025 source.** `parse/y2025_sec.py` reads the
mandal-level E and A reports into `2025/sarpanch_results.parquet` (one row per
GP) and `2025/sarpanch_candidates.parquet`. The district reports name no
mandal and GP names repeat within districts, so they serve only as an
independent count. The form's `getMandal` call omits 37 mandals created after
2019; the collector adds the mandals listed on the report page itself.

**Eenadu** (`2025/eenadu_results.parquet`) is kept as an independent check:
a newspaper's compilation in Telugu, with the party it says backed each
winner, and no reservation.

## Columns

Seat tables (`*/sarpanch_results.parquet`) use the pooled schema of
in-rolls/local_elections:

| Column | Meaning |
|---|---|
| `state`, `year` | Telangana; 2019 or 2025 |
| `district`, `block`, `gram_panchayat` | As printed. `block` is the mandal. 2025: names from the SEC form's dropdowns |
| `tier`, `tier_local` | `gp_head`, `sarpanch` |
| `reservation_raw` | The SEC code, e.g. `ST(W)` |
| `caste_reservation` | The **seat's** category: `ST`, `SC`, `BC`, `NONE` (unreserved). Never the winner's caste |
| `woman_reserved` | 1 if the **seat** is reserved for a woman |
| `reservation` | Pooled label, e.g. `SC Woman`, `Other than Woman` |
| `winner` | As printed. Null where the source gives no name |
| `winner_basis` | `published` where the source names a result |
| `party` | 2019: the SEC's party column, `IND` on every row (the polls are formally non-party). 2025: null |
| `unopposed` | 2025: 1 where the A report lists one candidate and zero valid votes; null in 2019 |
| `script` | `latin` (SEC tables) or `telugu` (Eenadu) |
| `source_path`, `source_url`, `source_locator` | Committed raw file, its origin, and the position in it: `row N` (CSV record after the header) or `mandal block k, row r` (k-th mandal block on the page, r-th row of its table) |

`2025/sarpanch_results.parquet` also has (types and constraints in
[schemas/2025_sarpanch_results.json](schemas/2025_sarpanch_results.json),
checked on every `make data`):

| Column | Meaning |
|---|---|
| `district_id`, `mandal_id`, `gp_code` | The SEC's codes. `gp_code` is unique only within a mandal |
| `result_declared` | True where the E report names a winner (12,702). The 33 others have no nominations, no result, or a court stay |
| `in_reports` | `both`, or `candidates_only` for GPs in the A report alone |
| `listed_twice` | True for the 5 GPs the E report prints twice (same GP code and winner); the repeat is dropped |
| `reservation_raw_a`, `candidates`, `elected_count`, `elected_name` | From the A report: its reservation code, candidate count, how many are marked Elected, and who |
| `total_valid_votes`, `rejected_votes`, `tendered_votes`, `nota_votes` | From the A report's GP caption |
| `a_path`, `a_locator` | Where the GP is in the A report; `source_*` point to the E report |

`2025/sarpanch_candidates.parquet` ([schema](schemas/2025_sarpanch_candidates.json)):
one row per candidate: `district`, `block`, `gram_panchayat`, codes, `serial`,
`candidate`, `candidate_votes`, `elected`, provenance.

`2025/eenadu_results.parquet` has the seat columns (reservation empty) plus:

| Column | Meaning |
|---|---|
| `district_printed` | District heading as Eenadu printed it (Telugu) |
| `phase` | Polling phase: 1 (11 Dec), 2 (14 Dec), 3 (17 Dec) |
| `result_declared` | False for the 53 GPs where the page gives neither winner nor party |
| `backing_party`, `backing_party_printed` | Party Eenadu says backed the winner, read from its icon (`INC`, `BRS`, `BJP`, `CPI`, `CPM`, `TDP`, `OTH`) and as printed. A newspaper's attribution, not a legal fact |

`2019/sarpanch_candidates.parquet` keeps the open-data release's columns,
renamed: `district`, `block`, `gram_panchayat`, `district_id`, `mandal_id`,
`gp_code`, `candidate`, `candidate_votes`, `reservation_raw`,
`caste_reservation`, `woman_reserved`, `total_valid_votes`, `rejected_votes`,
`tendered_votes`, `nota_votes`, plus provenance. It uses the district names in
force before 2021 (Warangal Urban, Jayashankar).

## Known issues

- **Women's seats in 2025 are half of each category's seats per mandal,
  rounded down** (98% of mandal x category groups), so 45.9% of seats
  statewide are women's, against 50.0% in 2019.
- **Shaikpally (Jogulamba Gadwal, Yerravalli)**: the E report names a winner;
  the A report marks no candidate Elected. Kept as the E report has it.
- **Shayampet mandal (24 GPs)** is listed by Eenadu under Jayashankar
  Bhupalpally, with no results. The SEC counts it in Hanumakonda. Karimnagar
  (2) and Khammam (5) GPs held back by court order are in the SEC's tables and
  not in Eenadu's; one Nirmal GP is unexplained.
  The district column is kept as Eenadu printed it, so Hanumakonda shows
  −24 and Bhupalpally +24 against the SEC table.
- 2025 winners are mostly given names without surnames, as printed. 8 declared
  rows have no winner name.
- Two 2025 keys repeat: Khammam/పెనుబల్లి/విఎంబంజర (one undeclared row, one
  declared) and Mancherial/కోటపల్లి/వెల్మపల్లి (two different winners). Seven
  2019 keys repeat, all thandas (hamlets) sharing a name within a mandal.
  None are dropped.
- 2019 covers 94% of notified seats; the 710 missing seats are not identified.

## Checks

Generated by `make manifest` from `build/release.py`. An `external` check
compares against a figure published elsewhere; an `internal` one only shows the
file agrees with itself. `not_run` says why. The 30-row hand comparison for 2025
is in [checks/hand_2025/](checks/hand_2025/): `sample.csv` lists 30 seeded-random
rows with a verdict, and `sheet0-2.png` show each row as Chrome renders the
saved page. All 30 match, by eye. Per-district counts are in MANIFEST.json under
`eenadu_district_counts_vs_sec`.

<!-- checks:start -->

| Check | Appeals to | Status | Result |
| --- | --- | --- | --- |
| `2019_coverage_vs_notified` | external | pass | 12,018 elected sarpanches of 12,728 notified posts (94.4%). Source: TGSEC notification for the 2019 GP election, as reported: 12,728 sarpanch posts across 12,751 GPs (local_elections, common/reference.py). |
| `2019_key_unique` | internal | warn | 7 (district, mandal, GP) keys appear more than once (14 rows). Kept as printed: two GPs can share a name inside a mandal, and the listing has no GP code. |
| `2019_women_share_vs_statute` | external | pass | 50.02% of seats reserved for women; the Act requires 50% (rounded down where a category's count is odd). |
| `2019_winner_is_top_vote_getter` | external | pass | Of 9,954 GPs found in both the SEC elected listing and the open-data vote table (untied, votes > 0), the listed winner is the top vote-getter in 100.0%. Mismatches include spelling differences between the two releases. |
| `2019_ward_coverage_vs_notified` | external | warn | 49,823 ward members against 112,242 ward seats (44.4%); the listing covers part of the state. Source: Ward-member seats in the 2019 GP election as recorded in in-rolls/local_elections (data/telangana readme, 'vs published'). |
| `2019_ward_key_and_women_share` | internal | warn | (district, mandal, GP, ward) repeats on 26 rows; 51.09% of wards reserved for women; 12,977 filled unanimously. |
| `2025_table_schema` | internal | pass | Each 2025 table matches its Table Schema in data/schemas/ (Arrow types, required fields, codes, keys). Failing: none. |
| `2025_mandal_reports_vs_district_reports` | internal | pass | GPs in the mandal reports against the district reports, per district and report: 0 of 62 differ (mandal total 25,442, district total 25,442). |
| `2025_elected_report_vs_candidates_report` | internal | pass | Of 12,702 GPs in both mandal reports, the E report's winner is the A report's 'Elected' candidate in 99.99%. Only in E: 0; only in A: 33. |
| `2025_reservation_same_in_both_reports` | internal | pass | Reservation code agrees between the E and A reports for 12,702 of 12,702 GPs. |
| `2025_elected_is_top_vote_getter` | internal | pass | In 11,466 contested GPs without a tie for first, the candidate marked Elected has the most votes in 100.00%. Candidates' votes add up to the caption's valid votes in 99.92% of 12,704 GPs. |
| `2025_key_unique` | internal | pass | 0 (district, mandal, GP) names appear more than once (0 rows). GPs without a GP code: 0. GPs the E report prints twice (repeat dropped): 5. |
| `2025_district_counts_vs_sec_phase_table` | external | pass | GPs per district against the SEC's September phase table (12,733 GPs): 0 district(s) differ by more than 1%. Districts not in the table: none. Total 12,735. |
| `2025_coverage_vs_notified` | external | pass | 12,735 GPs against 12,728 sarpanch posts notified (100.05%; the SEC's GP count is 12,735); with a declared winner: 12,702. |
| `2025_women_and_category_shares` | external | pass | Women's seats equal half the seats, rounded down, in 98.3% of 1,965 mandal x category groups; statewide 45.89% of seats are reserved for women. BC seats 2,178 of 12,735 (17.10%) against the SEC's reported 2,176 of 12,735 (17.08%; SEC figures reported by Siasat (article above) and South First, 'Telangana gram panchayat polls: BC quota slashed to 17 percent', https://thesouthfirst.com/telangana/telangana-gram-panchayat-polls-bc-quota-slashed-to-17-percent-amidst-backlash-over-betrayal-of-promises/). Rule: Telangana Panchayat Raj Act 2018 and G.O.Ms.No.46 (22 Nov 2025): 50% of seats in each category for women, rounded down where odd (South First, 'Telangana issues new reservation guidelines'). |
| `2025_district_counts_vs_eenadu` | external | warn | GPs per district, SEC minus Eenadu's newspaper tables (independent source): 5 of 31 districts differ; largest gap 24. Totals: SEC 12,735, Eenadu 12,727. |
| `eenadu_district_counts_vs_sec` | external | warn | Eenadu rows per district against the SEC phase table (31 districts, 12,733 GPs). 2 district(s) differ by more than 1%; largest absolute gap 24. Total rows 12,727. |
| `eenadu_coverage_vs_notified` | external | pass | 12,727 GP rows against 12,728 sarpanch posts notified (99.99%). Other published denominators: {'sec_phase_table_gps': 12733, 'gps_notified': 12735, 'sarpanch_posts_notified': 12728, 'gps_in_results_count': 12727}. |
| `eenadu_pages_internally_complete` | internal | pass | Every page's row count equals its printed panchayat total: True. Pages whose printed declared count is below their total: 17. |
| `eenadu_key_unique` | internal | warn | 2 (district, mandal, GP) keys appear more than once (4 rows). |
| `eenadu_backing_party_vs_siasat` | external | pass | Share of GPs by backing party, Eenadu minus Siasat: {'INC': -0.0004, 'BRS': 0.0001, 'BJP': 0.0001, 'OTH': 0.0002}. Eenadu counts {'INC': 6804, 'BRS': 3514, 'OTH': 1653, 'BJP': 703} of 12,674; Siasat {'INC': 6822, 'BRS': 3519, 'BJP': 703, 'OTH': 1654} of 12,698 (declared results only). Both are newspaper tallies, so agreement shows the parse is faithful, not that either is official. Siasat, 18 Dec 2025 (article above): Congress-backed 6,822 (53.60%), BRS 3,519, BJP-backed 703, independents and others 1,654. |
| `link_preview_2019_2025` | internal | info | 2025 GP names found among 2019 GP names of the same district group: exact (folded) 87.7%; loose (vowel length, aspiration, v/w, s/sh collapsed) 89.7%; loose against a different district's names (chance benchmark) 4.5%. District groups absorb the 2019 and 2021 reorganisations. Groups in one year only: ['Medchal-Malkajgiri']. |

<!-- checks:end -->
