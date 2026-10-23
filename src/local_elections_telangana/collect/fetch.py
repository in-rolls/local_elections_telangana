"""Polite, resumable fetching with a receipt for every saved response.

Every response that is kept is written once under data/raw/ and logged in
data/raw/fetch_log.csv with its URL, sha256, size, HTTP status and UTC fetch
time. A path already in the log is never fetched again, so an interrupted run
resumes where it stopped and a re-run cannot silently replace a source.
"""

import csv
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw"
LOG = RAW / "fetch_log.csv"
# The first six are local_elections docs/layout.md's required columns.
FIELDS = [
    "path",
    "url",
    "sha256",
    "bytes",
    "fetched_at_utc",
    "method",
    "source",
    "status",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (research data collection; in-rolls)"}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def logged():
    if not LOG.exists():
        return {}
    with LOG.open(encoding="utf-8") as fh:
        return {row["path"]: row for row in csv.DictReader(fh)}


def record(rel, url, source, status):
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        path = ROOT / rel
        writer.writerow(
            {
                "path": rel,
                "url": url,
                "source": source,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "status": status,
                "fetched_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "method": "wayback" if "web.archive.org" in source else "live",
            }
        )


def contained(rel):
    """ROOT/rel, refusing any path that resolves outside data/raw/.

    Local names are built from text the server returns (option values, document
    paths), so a hostile or malformed response must not be able to write
    anywhere else.
    """
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(RAW.resolve()):
        raise ValueError(f"refusing to write outside data/raw/: {rel!r}")
    return path


def save(content, rel, url, source, status):
    """Write a response body obtained some other way (e.g. a POST) and log it."""
    path = contained(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    record(rel, url, source, status)
    return path


def fetch(url, rel, source, session=None, delay=2.0, retries=3, timeout=60):
    """Save url to ROOT/rel unless already logged; return the local path."""
    path = contained(rel)
    if rel in logged() and path.exists():
        return path
    session = session or requests.Session()
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(delay * attempt * 3)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(delay * attempt * 5)
            continue
        resp.raise_for_status()
        save(resp.content, rel, url, source, resp.status_code)
        time.sleep(delay)
        return path
    raise RuntimeError(f"gave up on {url} after {retries} attempts")
