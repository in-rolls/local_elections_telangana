"""Collect pinned GHMC PDF sources, without replacing retained bytes."""

import csv
from datetime import UTC, datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from wayback import WaybackClient, WaybackSession

from local_elections_telangana.parse.ghmc import RAW, ROOT, sha

SOURCES = {
    "candidate_results_2016.pdf": "https://www.myghmc.com/assets/GHMCResult2016.pdf",
    "candidate_results_2020.pdf": "https://newsmeter.in/pdf_upload/pdf_upload-288883.pdf",
    "candidate_profiles_2020.pdf": "https://tsec.gov.in/pdf/proforma-5GHMC.pdf",
}


def collect():
    log = ROOT / "data/raw/fetch_log.csv"
    with log.open() as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        receipts = {r["path"]: r for r in reader}
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=2, status_forcelist=[429, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "Mozilla/5.0 (election research archive)"
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = RAW / name
        relative = str(path.relative_to(ROOT))
        if path.exists():
            if relative not in receipts or sha(path) != receipts[relative]["sha256"]:
                raise ValueError(f"Unlogged or changed retained file: {path}")
            continue
        source, method = url, "live"
        if name == "candidate_profiles_2020.pdf":
            client = WaybackClient(WaybackSession(retries=1, timeout=25))
            records = list(
                client.search(url, filter_field="statuscode:200", collapse="digest")
            )
            chosen = [
                r
                for r in records
                if r.timestamp.strftime("%Y%m%d%H%M%S") == "20201129111559"
            ]
            if len(chosen) != 1:
                raise ValueError("Pinned2020 candidate-profile capture unavailable")
            payload = client.get_memento(chosen[0]).content
            source, method = chosen[0].raw_url, "wayback"
        else:
            response = session.get(url, timeout=40)
            response.raise_for_status()
            payload, source = response.content, response.url
        if not payload.startswith(b"%PDF"):
            raise ValueError(f"Not a PDF: {url}")
        temp = path.with_suffix(".part")
        temp.write_bytes(payload)
        temp.replace(path)
        with log.open("a") as stream:
            csv.DictWriter(stream, fieldnames=fields, lineterminator="\n").writerow(
                {
                    "path": relative,
                    "url": url,
                    "source": source,
                    "sha256": sha(path),
                    "bytes": len(payload),
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                    "method": method,
                    "status": "200",
                }
            )
        print(f"Saved {relative}: {len(payload)} bytes")


if __name__ == "__main__":
    collect()
