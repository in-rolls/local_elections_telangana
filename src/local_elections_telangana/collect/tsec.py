"""Collect the commission's own 2025 sarpanch results. Needs an Indian connection.

tsec.gov.in refuses TCP connections from outside India (all three addresses it
resolves to time out; checked 2026-10-18 from the US). This collector has
therefore NOT been run. It is written against the form on
https://tsec.gov.in/knowPRRural.do as archived by the Internet Archive on
2025-11-17 and 2026-03-09, and the first run should be watched: the response
layout is assumed, not seen.

The 2019 elected-sarpanch file in this repository has exactly the columns this
page's "Only Elected Candidates" report prints, which is why it is the target.

Flow, as the page's own JavaScript does it:
1. GET knowPRRural.do -> session cookie and Struts token.
2. POST knowPRRural.do?mode=getElectionFor&year_id=2025&knowYour=S -> <option>s;
   keep the one naming the 2025 ordinary gram panchayat election.
3. For each district, POST knowPRRural.se with mode=getSarpanchDetails and
   typeOfReport E (elected only) and A (all contested candidates). Mandal and
   GP are left at 0, which the page's JavaScript allows for sarpanch reports.

Run: python -m local_elections_telangana.collect.tsec
"""

import re
import time

import requests

from local_elections_telangana.collect.fetch import HEADERS, logged, save

BASE = "https://tsec.gov.in"
# knowPRRural.do district ids; 21 Medchal-Malkajgiri and 22 Hyderabad held no
# 2025 gram panchayat election.
DISTRICTS = [f"{i:02d}" for i in range(1, 34) if i not in (21, 22)]
TOKEN = re.compile(r'name="org\.apache\.struts\.taglib\.html\.TOKEN" value="(\w+)"')
OPTION = re.compile(r'<option value="([^"]+)"[^>]*>([^<]+)</option>')


def token(html):
    found = TOKEN.search(html)
    if not found:
        raise RuntimeError("no Struts token on the page; the form has changed")
    return found.group(1)


def main(delay=3.0):
    s = requests.Session()
    s.headers.update(HEADERS)
    page = s.get(f"{BASE}/knowPRRural.do", timeout=60)
    page.raise_for_status()
    tok = token(page.text)
    opts = s.post(
        f"{BASE}/knowPRRural.do?mode=getElectionFor&year_id=2025&knowYour=S",
        timeout=60,
    ).text
    save(
        opts.encode(),
        "data/raw/2025/tsec/election_options.html",
        f"{BASE}/knowPRRural.do?mode=getElectionFor&year_id=2025&knowYour=S",
        "tsec.gov.in",
        200,
    )
    chosen = [
        (v, t) for v, t in OPTION.findall(opts) if "GRAM" in t.upper() and v != "0"
    ]
    if len(chosen) != 1:
        raise RuntimeError(f"expected one 2025 GP election option, got {chosen}")
    election = chosen[0][0]
    done = logged()
    for report in ("E", "A"):
        for district in DISTRICTS:
            rel = f"data/raw/2025/tsec/report_{report}/district_{district}.html"
            if rel in done:
                continue
            form = {
                "org.apache.struts.taglib.html.TOKEN": tok,
                "mode": "getSarpanchDetails",
                "property(knowYour)": "S",
                "property(year)": "2025",
                "property(electionFor)": election,
                "property(district_id)": district,
                "property(mandal_id)": "0",
                "property(mptc)": "0",
                "property(gpcode)": "0",
                "property(typeOfReport)": report,
            }
            resp = s.post(f"{BASE}/knowPRRural.se", data=form, timeout=120)
            resp.raise_for_status()
            url = (
                f"{BASE}/knowPRRural.se?mode=getSarpanchDetails&year=2025"
                f"&electionFor={election}&district_id={district}"
                f"&typeOfReport={report}"
            )
            save(resp.content, rel, url, "tsec.gov.in (POST)", resp.status_code)
            # Struts rotates the token per response
            tok = token(resp.text) if TOKEN.search(resp.text) else tok
            time.sleep(delay)


if __name__ == "__main__":
    main()
