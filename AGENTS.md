# Working on this data repository

This is a point-in-time data collection. Follow the [data-repository policy](https://github.com/soodoku/data-repos#maintenance-policy).

- Preserve sources, collection dates, provenance, schemas and reproducible parsing commands. Every fetched file is logged in `data/raw/fetch_log.csv` with its sha256 and fetch time; never overwrite one.
- Run `make check` once when code, inputs or outputs change. It needs `pdftotext` (poppler) for the SEC table.
- Keep scraping explicit (`make collect`). `make collect-tsec` needs an Indian connection.
- Names are kept in the script they were printed in (Telugu for 2025). Do not transliterate in place; transliteration belongs in a derived file.
- Do not add blanket CI, recurring dependency checks, version matrices, Docker/VM checks, pre-commit, Preen or package-release scaffolding.
- Ask when source meaning or credentials are unclear. Never infer substantive data values to make a check pass.
