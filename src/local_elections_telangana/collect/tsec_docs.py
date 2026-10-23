"""Collect the commission's published result, reservation and report documents.

Needs an Indian connection, as collect/tsec.py does.

The site's left menu (home.do) lists its documents under service ids; each id
is a POST to getData.se, and each document on the returned page is a GET of
download.do?fileName=<base64 path>. Read 2026-10-18. This saves every menu
page as returned, then downloads the documents whose path or title marks them
as results, reservations or election reports (SELECT below). Nothing is parsed
here.

Every saved file is logged in data/raw/fetch_log.csv with its sha256 and a
logged path is not fetched again, so a rerun resumes.
data/search_log/tsec_docs_index.csv lists each document's title, the menu pages
that link it and its site path.

Run: python -m local_elections_telangana.collect.tsec_docs
"""

import base64
import csv
import html
import logging
import re
import time
from urllib.parse import quote

from local_elections_telangana.collect.fetch import ROOT, logged, save
from local_elections_telangana.collect.tsec import BASE, TOKEN, session

OUT = "data/raw/tsec_docs"
INDEX = "data/search_log/tsec_docs_index.csv"
MENU_ID = re.compile(r"getLeftMenuData\('([0-9a-f]{32})'\)[^>]*>([^<]*)")
DOC = re.compile(r"getDownload\('([A-Za-z0-9+/=]+)'\)\"?[^>]*>(.*?)</a>", re.S)
# Site folders (the part after /Uploads/TSEC/pdf/) kept whole, and folders
# kept only for documents whose title matches.
WHOLE = {
    "StatisticalRep",
    "Sarpanch",
    "mptc",
    "zptc",
    "ANNUAL REPORT",
    "StatisticalReportsAnnualReport",
}
BY_TITLE = {
    "RLBS_GPs": re.compile(
        r"Reservation"
        r"|Notification issued for conduct of Elections to the offices of Sarpanch",
        re.I,
    ),
}

log = logging.getLogger("tsec_docs")


def decode(token):
    return base64.b64decode(token + "=" * (-len(token) % 4)).decode("utf-8", "replace")


def folder(path):
    parts = path.split("/")
    return parts[4] if len(parts) > 4 else ""


def wanted(path, title):
    top = folder(path)
    return top in WHOLE or bool(BY_TITLE.get(top) and BY_TITLE[top].search(title))


def local_name(path):
    rel = path.split("/pdf/", 1)[-1]
    return f"{OUT}/files/{rel}"


def crawl_menu(s, done, delay):
    home = s.get(f"{BASE}/home.do", timeout=120)
    home.raise_for_status()
    rel = f"{OUT}/menu/home.html"
    if rel not in done:
        save(home.content, rel, f"{BASE}/home.do", "tsec.gov.in", home.status_code)
    labels = {}
    for sid, label in MENU_ID.findall(home.text):
        labels.setdefault(sid, label.strip())
    token = TOKEN.search(home.text)
    pages = {}
    for sid in sorted(labels):
        rel = f"{OUT}/menu/{sid}.html"
        if rel not in done:
            form = {"mode": "unspecified", "property(side_serviceid)": sid}
            if token:
                form["org.apache.struts.taglib.html.TOKEN"] = token.group(1)
            resp = s.post(f"{BASE}/getData.se", data=form, timeout=120)
            resp.raise_for_status()
            save(
                resp.content,
                rel,
                f"{BASE}/getData.se?side_serviceid={sid}",
                "tsec.gov.in (POST)",
                resp.status_code,
            )
            token = TOKEN.search(resp.text) or token
            time.sleep(delay)
        pages[sid] = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    log.info("%d menu pages", len(pages))
    return labels, pages


def main(delay=2.0):
    (ROOT / OUT).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(ROOT / OUT / "collect.log"),
        ],
    )
    done = logged()
    s = session()
    labels, pages = crawl_menu(s, done, delay)

    docs = {}
    for sid, text in pages.items():
        for token, title in DOC.findall(text):
            path = decode(token)
            title = re.sub(r"<[^>]+>|\s+", " ", html.unescape(title)).strip()
            entry = docs.setdefault(
                path, {"token": token, "title": title, "pages": set()}
            )
            entry["pages"].add(labels.get(sid, sid))
    chosen = {p: d for p, d in docs.items() if wanted(p, d["title"])}
    log.info("%d documents linked, %d selected", len(docs), len(chosen))

    failed = 0
    for path, d in sorted(chosen.items()):
        rel = local_name(path)
        if rel in done:
            continue
        url = f"{BASE}/download.do?fileName={quote(d['token'], safe='')}"
        try:
            resp = s.get(url, timeout=600)
            resp.raise_for_status()
        except Exception as exc:  # keep going; the log names what is missing
            failed += 1
            log.warning("failed %s: %s", path, exc)
            continue
        if (
            resp.headers.get("content-type", "").startswith("text/html")
            and b"<html" in resp.content[:2000].lower()
        ):
            failed += 1
            log.warning("got an HTML page instead of a document for %s", path)
            continue
        save(resp.content, rel, url, "tsec.gov.in", resp.status_code)
        log.info("saved %s (%d bytes)", rel, len(resp.content))
        time.sleep(delay)

    with (ROOT / INDEX).open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["title", "menu_pages", "site_path", "local_path", "selected"])
        for path, d in sorted(docs.items()):
            writer.writerow(
                [
                    d["title"],
                    "; ".join(sorted(d["pages"])),
                    path,
                    local_name(path) if path in chosen else "",
                    int(path in chosen),
                ]
            )
    log.info("done: %d selected, %d failed", len(chosen), failed)


if __name__ == "__main__":
    main()
