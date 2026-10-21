"""Collect the commission's own 2025 sarpanch results. Needs an Indian connection.

tsec.gov.in refuses TCP connections from outside India (checked 2026-10-18:
it answers an Indian probe and times out from 35 other countries). Run this
from India, or through a proxy there, e.g. an SSH tunnel to a VM in
asia-south1 with HTTPS_PROXY=socks5h://localhost:1080 (needs PySocks).

The form is https://tsec.gov.in/knowPRRural.do ("Know your Public
Representative - Rural"). Its live JavaScript (read 2026-10-18) uses the
"...new" request modes; the older modes, as in the 2025 archived copy, return
an empty table for 2025. Flow:

1. GET knowPRRural.do -> session cookie, Struts token, district list.
2. POST knowPRRural.do?mode=getElectionFornew&year_id=2025&knowYour=S -> the
   election id ("ORDINARY ELECTIONS TO GRAM PANCHAYATHS, 2025").
3. GP frame: per district getMandal, per mandal getGramPanchayat. These are the
   dropdowns' GP lists, kept as an independent count to check the reports.
4. Reports: per district, POST knowPRRural.se mode=getSarpanchDetailsnew with
   typeOfReport E (elected: GP, reservation, winner) and A (all candidates
   with votes, plus valid/rejected/NOTA votes per GP). A district whose report
   has fewer GPs than its frame is fetched again mandal by mandal.

Every saved response is logged in data/raw/fetch_log.csv (sha256, time) and a
path already logged is not fetched again, so a rerun resumes. Progress and
warnings go to data/raw/2025/tsec/collect.log.

Run: python -m local_elections_telangana.collect.tsec
"""

import gzip
import logging
import re
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from local_elections_telangana.collect.fetch import HEADERS, ROOT, logged, save

BASE = "https://tsec.gov.in"
OUT = "data/raw/2025/tsec"
YEAR = "2025"
TOKEN = re.compile(r'name="org\.apache\.struts\.taglib\.html\.TOKEN" value="(\w+)"')
OPTION = re.compile(r'<option value="([^"]*)"[^>]*>([^<]*)</option>')
DISTRICT_SELECT = re.compile(r'id="district_id"[^>]*>(.*?)</select>', re.S)
MANDAL_SELECT = re.compile(r'id="mandal_id"[^>]*>(.*?)</select>', re.S)
# Data rows of the elected report start with a serial number; the
# all-candidates report opens each GP with a "Gram Panchayat :" caption row.
ELECTED_ROW = re.compile(r"<tr[^>]*>\s*<td[^>]*>\s*\d+\s*</td>")
CANDIDATE_GP = re.compile(r"Gram Panchayat\s*:")

# The form's offices (knowYour) and their report modes, from the live page's
# JavaScript (read 2026-10-21). Ward members (GW) have an elected report only:
# typeOfReport=A returns the form without a grid.
MODES = {"S": "getSarpanchDetailsnew", "GW": "getGPWardDetailsnew"}

log = logging.getLogger("tsec")


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(
        total=6,
        connect=6,
        read=6,
        backoff_factor=5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=None,  # retry POSTs too: every request here only reads
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def options(html):
    """The dropdown's (id, label) pairs. Ids become file names, so only digits."""
    return [(v, t.strip()) for v, t in OPTION.findall(html) if v.isdigit() and v != "0"]


class Client:
    """One browser-like session: cookie, rotating Struts token, polite delay."""

    def __init__(self, delay):
        self.delay = delay
        self.start()

    def start(self):
        self.s = session()
        page = self.s.get(f"{BASE}/knowPRRural.do", timeout=120)
        page.raise_for_status()
        self.page = page.text
        found = TOKEN.search(page.text)
        if not found:
            raise RuntimeError("no Struts token on the form; the page has changed")
        self.token = found.group(1)

    def ajax(self, query):
        resp = self.s.post(f"{BASE}/knowPRRural.do?{query}", timeout=120)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def report(self, election, district, mandal, kind, office="S"):
        form = {
            "org.apache.struts.taglib.html.TOKEN": self.token,
            "mode": MODES[office],
            "property(knowYour)": office,
            "property(year)": YEAR,
            "property(electionFor)": election,
            "property(district_id)": district,
            "property(mandal_id)": mandal,
            "property(mptc)": "0",
            "property(gpcode)": "0",
            "property(typeOfReport)": kind,
        }
        resp = self.s.post(f"{BASE}/knowPRRural.se", data=form, timeout=300)
        resp.raise_for_status()
        found = TOKEN.search(resp.text)
        if found:
            self.token = found.group(1)
        time.sleep(self.delay)
        return resp


def gp_count(html, kind):
    pattern = ELECTED_ROW if kind == "E" else CANDIDATE_GP
    return len(pattern.findall(html))


def read(rel):
    """A saved page; committed pages are gzipped (rel + ".gz")."""
    path = ROOT / rel
    if not path.exists():
        return gzip.decompress((ROOT / f"{rel}.gz").read_bytes()).decode(
            "utf-8", "replace"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def cached(client, query, rel, done):
    if rel not in done:
        resp = client.ajax(query)
        save(
            resp.content,
            rel,
            f"{BASE}/knowPRRural.do?{query}",
            "tsec.gov.in (POST)",
            200,
        )
        done[rel] = True
    return read(rel)


def fetch_report(
    client, election, district, mandal, kind, rel, done, attempts=3, office="S"
):
    """Fetch one report; a page without the results grid is retried in a new session."""
    if rel in done:
        return read(rel)
    url = (
        f"{BASE}/knowPRRural.se?mode={MODES[office]}&knowYour={office}&year={YEAR}"
        f"&electionFor={election}&district_id={district}&mandal_id={mandal}"
        f"&typeOfReport={kind}"
    )
    nogrid = rel.replace(".html", ".nogrid.html")
    if nogrid in done:
        return ""
    for attempt in range(1, attempts + 1):
        resp = client.report(election, district, mandal, kind, office)
        if 'id="GridView1"' in resp.text:
            save(resp.content, rel, url, "tsec.gov.in (POST)", resp.status_code)
            done[rel] = True
            return resp.text
        log.warning("%s: no results grid (attempt %d); new session", rel, attempt)
        if attempt < attempts:
            time.sleep(30 * attempt)
            client.start()
    # A mandal with no GPs (an urban mandal) legitimately has no table. Keep the
    # page as evidence under its own name so the parser can tell it apart.
    save(resp.content, nogrid, url, "tsec.gov.in (POST)", resp.status_code)
    done[nogrid] = True
    log.warning("%s: saved without a results grid", nogrid)
    return ""


def report_mandals(html):
    """The (id, label) pairs in a report page's own mandal dropdown."""
    found = MANDAL_SELECT.search(html)
    return options(found.group(1)) if found else []


def collect_district(client, election, district, name, done):
    q = f"mode=getMandal&district_id={district}"
    mandals = options(cached(client, q, f"{OUT}/frame/mandals_{district}.html", done))
    # getMandal omits mandals created after 2019 (37 statewide, checked
    # 2026-10-19); the report page's own dropdown lists them. Read the
    # district report first and add its mandals, so their GPs get a mandal
    # report too.
    rel = f"{OUT}/report_E/district_{district}.html"
    page = fetch_report(client, election, district, "0", "E", rel, done)
    known = {m for m, _ in mandals}
    mandals += [(m, n) for m, n in report_mandals(page) if m not in known]
    frame = 0
    for mandal, _ in mandals:
        q = f"mode=getGramPanchayat&district_id={district}&mandal_id={mandal}"
        frame += len(
            options(
                cached(client, q, f"{OUT}/frame/gps_{district}_{mandal}.html", done)
            )
        )
    row = {"district": district, "name": name, "mandals": len(mandals), "frame": frame}
    # The district report names no mandal, and GP names repeat across mandals
    # within a district, so the mandal reports are what key a GP. The district
    # report is kept as an independent count of the same GPs.
    for kind in ("E", "A"):
        rel = f"{OUT}/report_{kind}/district_{district}.html"
        whole = gp_count(
            fetch_report(client, election, district, "0", kind, rel, done), kind
        )
        parts = 0
        for mandal, _ in mandals:
            rel = f"{OUT}/report_{kind}/by_mandal/district_{district}_{mandal}.html"
            parts += gp_count(
                fetch_report(client, election, district, mandal, kind, rel, done),
                kind,
            )
        if parts != whole:
            log.warning(
                "%s %s: mandal reports %d GPs, district report %d",
                name,
                kind,
                parts,
                whole,
            )
        row[kind] = parts
        row[f"{kind}_district_report"] = whole
    return row


def collect_wards(client, election, district, name, done):
    """Every mandal's ward-member report. The mandal list is the sarpanch run's:
    the getMandal frame plus the mandals only the report dropdown lists."""
    mandals = options(read(f"{OUT}/frame/mandals_{district}.html"))
    known = {m for m, _ in mandals}
    page = read(f"{OUT}/report_E/district_{district}.html")
    mandals += [(m, n) for m, n in report_mandals(page) if m not in known]
    # TSEC has not published wards for every mandal: Adilabad's district report
    # lists 292 of its GPs, and mandals such as Bheempur return the form without
    # a grid even for a single GP. The district report is kept as a second count,
    # and an empty mandal is tried once - a gap in the source, not a transient
    # error.
    rel = f"{OUT}/ward_E/district_{district}.html"
    page = fetch_report(client, election, district, "0", "E", rel, done, office="GW")
    whole = len(ELECTED_ROW.findall(page))
    wards = 0
    for mandal, _ in mandals:
        rel = f"{OUT}/ward_E/by_mandal/district_{district}_{mandal}.html"
        page = fetch_report(
            client, election, district, mandal, "E", rel, done, attempts=1, office="GW"
        )
        wards += len(ELECTED_ROW.findall(page))
    if wards != whole:
        log.warning(
            "%s: mandal reports %d wards, district report %d", name, wards, whole
        )
    row = {"district": district, "name": name, "mandals": len(mandals), "wards": wards}
    row["district_report"] = whole
    log.info("%s", row)
    return row


def main(delay=2.0, office="S"):
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
    client = Client(delay)
    districts = [
        (d, n)
        for d, n in options(DISTRICT_SELECT.search(client.page).group(1))
        if d.isdigit()
    ]
    log.info("%d districts on the form", len(districts))

    q = f"mode=getElectionFornew&year_id={YEAR}&knowYour={office}"
    name = (
        "election_options.html" if office == "S" else f"election_options_{office}.html"
    )
    opts = options(cached(client, q, f"{OUT}/{name}", done))
    chosen = [v for v, t in opts if "GRAM PANCHAYAT" in t.upper()]
    if len(chosen) != 1:
        raise RuntimeError(f"expected one {YEAR} GP election option, got {opts}")
    election = chosen[0]
    log.info("election id %s", election)

    if office == "GW":
        rows = [collect_wards(client, election, d, n, done) for d, n in districts]
        log.info("totals: %d ward rows", sum(r["wards"] for r in rows))
        return
    summary = []
    for district, name in districts:
        row = collect_district(client, election, district, name, done)
        log.info("%s", row)
        summary.append(row)
    log.info(
        "totals: frame %d, elected report %d, all-candidates report %d",
        sum(r["frame"] for r in summary),
        sum(r["E"] for r in summary),
        sum(r["A"] for r in summary),
    )
    for r in summary:
        if r["E"] != r["E_district_report"] or r["A"] != r["A_district_report"]:
            log.warning("mandal and district reports disagree %s", r)


if __name__ == "__main__":
    import sys

    main(office="GW" if "--wards" in sys.argv else "S")
