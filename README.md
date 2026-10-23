# Telangana Sarpanch Elections

[![Code license: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)

Telangana's gram panchayat head (sarpanch) elections of 2019 and December 2025:
one row per sarpanch seat, with the seat's reservation and its winner. Every row
points back to the file, URL and position it was read from. The raw sources
are committed under [data/raw/](data/raw/).

This is a sister repository of [in-rolls/local_elections](https://github.com/in-rolls/local_elections).
Column names follow that repository's pooled schema.

## Status: read this first

| | 2019 | 2025 |
|---|---|---|
| Seats | 12,018 of 12,728 notified (94%) | 12,735 GPs, the SEC's full count; 12,702 with a declared winner |
| Reservation (caste + women) | yes, from the State Election Commission's (SEC) listing | yes, from the SEC's results reports |
| Winner | yes (Latin script) | yes (Latin script), plus every candidate's votes |
| Source | SEC listing + Telangana Open Data candidate votes | SEC results reports (tsec.gov.in, collected through a VM in Mumbai), checked against Eenadu's newspaper tables |

The SEC's site refuses connections from outside India. Both SEC collectors
were run on 2026-10-18 and 2026-10-19 through an SSH tunnel to a Google Cloud
VM in Mumbai (`gcloud compute ssh <vm> -- -N -D 1080`, then
`HTTPS_PROXY=socks5h://localhost:1080 make collect-tsec` and
`make collect-tsec-docs`; PySocks is in the `collect` dependency group):

- [collect/tsec.py](src/local_elections_telangana/collect/tsec.py): the 2025
  elected and all-candidates reports, per district and per mandal, and the
  form's mandal and GP lists.
- [collect/tsec_docs.py](src/local_elections_telangana/collect/tsec_docs.py):
  106 result, reservation and report documents (sarpanch winners for 1995, 2001,
  2006, 2013 and 2019; reservations for 2013 and 2019; election reports).

## Data

| File | Rows | Each row is |
|---|---:|---|
| [release/2019/sarpanch_results.parquet](data/release/2019/sarpanch_results.parquet) | 12,018 | an elected sarpanch and their seat's reservation |
| [release/2019/sarpanch_candidates.parquet](data/release/2019/sarpanch_candidates.parquet) | 35,121 | a contesting candidate's votes (12,137 GPs) |
| [release/2019/ward_results.parquet](data/release/2019/ward_results.parquet) | 49,823 | an elected ward member and their seat's reservation |
| [release/2025/sarpanch_results.parquet](data/release/2025/sarpanch_results.parquet) | 12,735 | a GP in the December 2025 election: reservation, winner, votes (SEC) |
| [release/2025/ward_results.parquet](data/release/2025/ward_results.parquet) | 62,990 | an elected ward member in 2025 and their ward's caste reservation (SEC); no women's reservation, sex or votes are printed, and TSEC published wards for 7,140 of 12,735 GPs |
| [release/2025/sarpanch_candidates.parquet](data/release/2025/sarpanch_candidates.parquet) | 39,207 | a contesting candidate's votes (SEC) |
| [release/2025/eenadu_results.parquet](data/release/2025/eenadu_results.parquet) | 12,727 | a GP and its winner as Eenadu printed them (Telugu) |
| [release/2025/eenadu_mandal_counts.parquet](data/release/2025/eenadu_mandal_counts.parquet) | 563 | a mandal block on an Eenadu page, with its printed counts |
| [release/2025/eenadu_page_counts.parquet](data/release/2025/eenadu_page_counts.parquet) | 93 | an Eenadu page (district × phase), with its printed counts |

Column definitions, sources, and every check with its result are in
[data/README.md](data/README.md). [data/MANIFEST.json](data/MANIFEST.json)
records the hash, row count and schema of each output, the hash and fetch time
of each raw file, and the check results.

```python
import pandas as pd

s19 = pd.read_parquet("data/release/2019/sarpanch_results.parquet")
s25 = pd.read_parquet("data/release/2025/sarpanch_results.parquet")
s19.groupby("reserved_caste")["reserved_woman"].mean()
s25.groupby(["reserved_caste", "reserved_woman"]).size()
```

## Links between elections

[data/release/linkage/](data/release/linkage/) links 11,464 of the 12,018 2019 seats to their
2025 seats, by the commission's codes and by GP names, and says how well the
two agree.

## Reproducing

```
make sync      # uv environment
make data      # parse the committed raw files, link 2019 to 2025, rebuild MANIFEST.json and the checks
make check     # ruff + hash and check verification
make collect   # network: fetch anything missing from data/raw/fetch_log.csv
```

`make check` needs `pdftotext` (poppler), which reads the SEC's per-district
table straight from its PDF.
