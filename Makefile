PY = .venv/bin/python
RUFF = .venv/bin/ruff

.PHONY: sync collect collect-tsec collect-tsec-docs data link infer manifest lint verify check

sync:
	uv sync --frozen --all-groups

# network: fetches only what fetch_log.csv does not already hold
collect:
	$(PY) -m local_elections_telangana.collect.sources_2025

# needs an Indian connection; never run from here (see collect/tsec.py)
collect-tsec:
	$(PY) -m local_elections_telangana.collect.tsec

collect-tsec-wards:
	$(PY) -m local_elections_telangana.collect.tsec --wards

collect-tsec-docs:
	$(PY) -m local_elections_telangana.collect.tsec_docs

data:
	$(PY) -m local_elections_telangana.parse.y2019
	$(PY) -m local_elections_telangana.parse.y2025
	$(PY) -m local_elections_telangana.parse.y2025_sec
	$(PY) -m local_elections_telangana.parse.y2025_wards
	$(PY) -m local_elections_telangana.build.contract
	$(PY) -m local_elections_telangana.linkage.gp_links
	$(MAKE) manifest

infer:
	$(PY) -m local_elections_telangana.infer.winner_sex

manifest:
	$(PY) -m local_elections_telangana.build.release write

lint:
	$(RUFF) check .
	$(RUFF) format --check .

verify:
	$(PY) -m local_elections_telangana.build.release verify

check: lint verify
