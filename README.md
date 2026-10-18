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
| Seats | 12,018 of 12,728 notified (94%) | 12,727 of 12,728 notified; 12,674 with a declared result |
| Reservation (caste + women) | yes, from the State Election Commission's (SEC) listing | **no.** Not in any source reachable from outside India |
| Winner | yes (Latin script) | yes, as Eenadu printed it (Telugu script; mostly given names only) |
| Source | SEC listing + Telangana Open Data candidate votes | **Eenadu** (newspaper) results tables, plus archived SEC notifications |

The 2025 file supports the "who won" half of the planned 2019→2025 analysis. It
does not support the "was the 2025 seat open" half. The SEC's own per-GP
results, with reservation, are at `https://tsec.gov.in/knowPRRural.do`, and
that site refuses connections from outside India. `make collect-tsec` is
written for someone on an Indian connection to run (see
[collect/tsec.py](src/local_elections_telangana/collect/tsec.py)). It has not
been run yet, so treat its first run as a test.

## Data

| File | Rows | Each row is |
|---|---:|---|
| [2019/sarpanch_results.parquet](data/2019/sarpanch_results.parquet) | 12,018 | an elected sarpanch and their seat's reservation |
| [2019/sarpanch_candidates.parquet](data/2019/sarpanch_candidates.parquet) | 35,121 | a contesting candidate's votes (12,137 GPs) |
| [2025/sarpanch_results.parquet](data/2025/sarpanch_results.parquet) | 12,727 | a GP in the December 2025 election and its winner |
| [2025/eenadu_mandal_counts.parquet](data/2025/eenadu_mandal_counts.parquet) | 563 | a mandal block on an Eenadu page, with its printed counts |
| [2025/eenadu_page_counts.parquet](data/2025/eenadu_page_counts.parquet) | 93 | an Eenadu page (district × phase), with its printed counts |

Column definitions, sources, and every check with its result are in
[data/README.md](data/README.md). [data/MANIFEST.json](data/MANIFEST.json)
records the hash, row count and schema of each output, the hash and fetch time
of each raw file, and the check results.

```python
import pandas as pd

s19 = pd.read_parquet("data/2019/sarpanch_results.parquet")
s25 = pd.read_parquet("data/2025/sarpanch_results.parquet")
s19.groupby("caste_reservation")["woman_reserved"].mean()
s25[s25["result_declared"]].groupby("backing_party").size()
```

## Reproducing

```
make sync      # uv environment
make data      # parse the committed raw files, rebuild MANIFEST.json and the checks
make check     # ruff + hash and check verification
make collect   # network: fetch anything missing from data/raw/fetch_log.csv
```

`make check` needs `pdftotext` (poppler), which reads the SEC's per-district
table straight from its PDF.
