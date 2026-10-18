# Data

## Sources

### 2019

| File | What | Origin |
|---|---|---|
| `raw/2019/2019_gp_sarpanch.csv` | 12,018 elected sarpanches with seat reservation codes (`UR/SC/ST/BC` × `(G)` general / `(W)` woman) | The columns are exactly those of the SEC's "Know your PR representative – Rural" report, `https://tsec.gov.in/knowPRRural.do` ("Only Elected Candidates"), with a District column added. Committed to in-rolls/local_elections on 2023-06-10, with no URL recorded. The URL is **inferred** from the column match and the post-2021 district names (Hanumakonda). |
| `raw/2019/grampanchayatelectionsdata_2019_sarpanch.csv` | 35,121 candidate rows: votes per candidate, plus valid, rejected and tendered votes and NOTA per GP, with SEC district/mandal/GP codes | Telangana Open Data Portal, `https://data.telangana.gov.in/dataset/telangana-gram-panchayat-sarpanch-election-data-2019` (recorded in local_elections' 2022 readme; the portal does not answer from outside India). |

Both files were copied unchanged from `local_elections/data/telangana/raw/`.
`raw_held` in MANIFEST.json gives their hashes.

### 2025

| Files | What | Origin |
|---|---|---|
| `raw/2025/sec/sec_notification_1085_2025-11-25_{english,telugu}.pdf` | SEC Notification 1085/TGSEC-PR/2025 calling the December election. It names 32 GPs held back by court orders (Mulugu 25, Karimnagar 2, Khammam 5). Annexure-II (counts by phase) is missing from the uploaded scan | tsec.gov.in via Internet Archive captures (`web.archive.org/web/<ts>id_/…`) |
| `raw/2025/sec/sec_phasewise_gp_elections_2025.pdf` | SEC phase-wise GP counts per district, 31 districts, 12,733 GPs (September 2025 schedule; the election was re-notified in November with new phases) | same |
| `raw/2025/eenadu/phase{1,2,3}/<district>.html` | Eenadu's results tables: per district and phase, a block per mandal, a row per GP: panchayat, winner, backing party | `https://www.eenadu.net/telangana/panchayat-elections-results-phase{p}/{district}` |

`raw/fetch_log.csv` records the URL, sha256, size, HTTP status and UTC fetch
time of every fetched file. The fetcher skips anything already logged.

**Why Eenadu.** The SEC's per-GP results (`knowPRRural.do`, `dashboardresults.do`)
are POST forms on tsec.gov.in. All three of its IP addresses refuse TCP
connections from outside India (tested 2026-10-18), and the Internet Archive
holds only the empty forms. Eenadu is the only complete per-GP compilation
found that can be reached. It is a newspaper's compilation, not an official
result, and it prints no reservation.

**What was looked for and not found:** the GO 46 reservation lists (district
collectorate sites carry at most September 2025 lists drawn under the
superseded 42% BC order, as scans: e.g. Khammam), data.telangana.gov.in
(unreachable from outside India), opencity.in, dataful.in, GitHub and Kaggle
(nothing for the 2025 GP poll).

## Columns

Seat tables (`*/sarpanch_results.parquet`) use the pooled schema of
in-rolls/local_elections:

| Column | Meaning |
|---|---|
| `state`, `year` | Telangana; 2019 or 2025 |
| `district`, `block`, `gram_panchayat` | As printed. `block` is the mandal. 2025 district names are mapped from Eenadu's URL slug to the SEC's spelling; 2025 `block` and `gram_panchayat` are Telugu |
| `tier`, `tier_local` | `gp_head`, `sarpanch` |
| `reservation_raw` | The SEC code, e.g. `ST(W)` (2019 only) |
| `caste_reservation` | The **seat's** category: `ST`, `SC`, `BC`, `NONE` (unreserved). Never the winner's caste |
| `woman_reserved` | 1 if the **seat** is reserved for a woman |
| `reservation` | Pooled label, e.g. `SC Woman`, `Other than Woman` |
| `winner` | As printed. Null where the source gives no name |
| `winner_basis` | `published` where the source names a result |
| `party` | 2019: the SEC's party column, `IND` on every row (the polls are formally non-party). 2025: null |
| `unopposed` | Not stated by either source; null |
| `script` | `latin` (2019) or `telugu` (2025) |
| `source_path`, `source_url`, `source_locator` | Committed raw file, its origin, and the position in it: `row N` (CSV record after the header) or `mandal block k, row r` (k-th mandal block on the page, r-th row of its table) |

2025 only:

| Column | Meaning |
|---|---|
| `district_printed` | District heading as Eenadu printed it (Telugu) |
| `phase` | Polling phase: 1 (11 Dec), 2 (14 Dec), 3 (17 Dec) |
| `result_declared` | False for the 53 GPs where the page gives neither winner nor party (no nominations, court stay or pending; Siasat reports 21 + 5 + 26) |
| `backing_party`, `backing_party_printed` | Party Eenadu says backed the winner, read from its icon (`INC`, `BRS`, `BJP`, `CPI`, `CPM`, `TDP`, `OTH`) and as printed. A newspaper's attribution, not a legal fact |

`2019/sarpanch_candidates.parquet` keeps the open-data release's columns,
renamed: `district`, `block`, `gram_panchayat`, `district_id`, `mandal_id`,
`gp_code`, `candidate`, `candidate_votes`, `reservation_raw`,
`caste_reservation`, `woman_reserved`, `total_valid_votes`, `rejected_votes`,
`tendered_votes`, `nota_votes`, plus provenance. It uses the district names in
force before 2021 (Warangal Urban, Jayashankar).

## Known issues

- **2025 has no reservation.** See above.
- **Shayampet mandal (24 GPs)** is listed by Eenadu under Jayashankar
  Bhupalpally, with no results. The SEC's table counts it in Hanumakonda.
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
`2025_district_counts_vs_sec`.

<!-- checks:start -->

| Check | Appeals to | Status | Result |
| --- | --- | --- | --- |
| `2019_coverage_vs_notified` | external | pass | 12,018 elected sarpanches of 12,728 notified posts (94.4%). Source: TGSEC notification for the 2019 GP election, as reported: 12,728 sarpanch posts across 12,751 GPs (local_elections, common/reference.py). |
| `2019_key_unique` | internal | warn | 7 (district, mandal, GP) keys appear more than once (14 rows). Kept as printed: two GPs can share a name inside a mandal, and the listing has no GP code. |
| `2019_women_share_vs_statute` | external | pass | 50.02% of seats reserved for women; the Act requires 50% (rounded down where a category's count is odd). |
| `2019_winner_is_top_vote_getter` | external | pass | Of 9,954 GPs found in both the SEC elected listing and the open-data vote table (untied, votes > 0), the listed winner is the top vote-getter in 100.0%. Mismatches include spelling differences between the two releases. |
| `2025_district_counts_vs_sec` | external | warn | Eenadu rows per district against the SEC phase table (31 districts, 12,733 GPs). 2 district(s) differ by more than 1%; largest absolute gap 24. Total rows 12,727. |
| `2025_coverage_vs_notified` | external | pass | 12,727 GP rows against 12,728 sarpanch posts notified (99.99%). Other published denominators: {'sec_phase_table_gps': 12733, 'gps_notified': 12735, 'sarpanch_posts_notified': 12728, 'gps_in_results_count': 12727}. |
| `2025_pages_internally_complete` | internal | pass | Every page's row count equals its printed panchayat total: True. Pages whose printed declared count is below their total: 17. |
| `2025_key_unique` | internal | warn | 2 (district, mandal, GP) keys appear more than once (4 rows). |
| `2025_women_and_category_shares` | external | not_run | No 2025 reservation source is parsed: Eenadu prints none, the commission's tables need an Indian connection, and the collectorate statements found are scans. Reference figures to use once it is: BC 2,176 of 12,735 (17.08%; SEC figures reported by Siasat (article above) and South First, 'Telangana gram panchayat polls: BC quota slashed to 17 percent', https://thesouthfirst.com/telangana/telangana-gram-panchayat-polls-bc-quota-slashed-to-17-percent-amidst-backlash-over-betrayal-of-promises/); women 50% (Telangana Panchayat Raj Act 2018 and G.O.Ms.No.46 (22 Nov 2025): 50% of seats in each category for women, rounded down where odd (South First, 'Telangana issues new reservation guidelines').). |
| `2025_backing_party_vs_siasat` | external | pass | Share of GPs by backing party, Eenadu minus Siasat: {'INC': -0.0004, 'BRS': 0.0001, 'BJP': 0.0001, 'OTH': 0.0002}. Eenadu counts {'INC': 6804, 'BRS': 3514, 'OTH': 1653, 'BJP': 703} of 12,674; Siasat {'INC': 6822, 'BRS': 3519, 'BJP': 703, 'OTH': 1654} of 12,698 (declared results only). Both are newspaper tallies, so agreement shows the parse is faithful, not that either is official. Siasat, 18 Dec 2025 (article above): Congress-backed 6,822 (53.60%), BRS 3,519, BJP-backed 703, independents and others 1,654. |
| `link_preview_2019_2025` | internal | info | 2025 names are Telugu, 2019 names Latin, so a raw exact match is 0 by construction. After rule-based Telugu->Latin transliteration (indic-transliteration, HK scheme): exact folded match within the same district name 22.2%; loose match (vowel length, aspiration, v/w, s/sh collapsed) within district 67.7%; loose match anywhere in the state 72.8%; loose match against a different district's 2019 names (chance benchmark) 4.3%. Districts are compared as groups that absorb renames and splits (Mulugu and Narayanpet were carved out in Feb 2019 and the 2019 listing files them under their parents; Hanumakonda and Warangal swapped mandals in 2021). Mandals are not used: 2025 mandal names are Telugu and several mandals were created after 2019. Unmatched district groups: ['Medchal-Malkajgiri']. |

<!-- checks:end -->
