"""Fetch every reachable 2025 source into data/raw/2025/.

Two kinds of source, in order of authority:

1. The State Election Commission's own documents. tsec.gov.in refuses TCP
   connections from outside India, so these come from Internet Archive captures
   (web.archive.org, the `id_` form, which returns the archived bytes
   unmodified). The URL logged is the capture URL; the original is inside it.
2. Eenadu's published results tables: one page per district per polling phase,
   one table per mandal, one row per gram panchayat (name, winner, the party
   said to have backed the winner). Telugu script. A newspaper's compilation,
   not an official result, and it carries no reservation category.

Run: python -m local_elections_telangana.collect.sources_2025
"""

import requests

from local_elections_telangana.collect.fetch import fetch

WAYBACK = "https://web.archive.org/web/{ts}id_/{url}"

# Captures found with the Wayback CDX API (url=tsec.gov.in/*). preview.do
# serves the PDF named by the base64 fileName parameter.
SEC_ARCHIVED = {
    # Notification 1085/TGSEC-PR/2025, 25.11.2025: calls the December election
    # and lists the 32 GPs held back by court orders. Annexure-II (counts by
    # district and phase) is not in the uploaded scan.
    "sec_notification_1085_2025-11-25_english.pdf": (
        "20251212175131",
        "https://tsec.gov.in/preview.do?fileName=L1VwbG9hZHMvVFNFQy9wZGYvZW5n"
        "bGlzaF9ub3RpZmljYXRpb25fbm8uMTA4NSxfZHQuMjUuMTEuMjAyNV81MDcucGRm",
    ),
    "sec_notification_1085_2025-11-25_telugu.pdf": (
        "20251212200028",
        "https://tsec.gov.in/preview.do?fileName=L1VwbG9hZHMvVFNFQy9wZGYvdGVs"
        "dWd1X25vdGlmaWNhdGlvbl9uby4xMDg1LF9kdC4yNS4xMS4yMDI1XzUwOC5wZGY=",
    ),
    # Phase-wise GP counts by district for the September 2025 schedule (later
    # held in abeyance and re-notified in November): 31 districts, 12,733 GPs.
    "sec_phasewise_gp_elections_2025.pdf": (
        "20251117091747",
        "https://tsec.gov.in/preview.do?fileName=L1VwbG9hZHMvVFNFQy9wZGYvcGhh"
        "c2V3aXNlX2dwX2VsZWN0aW9ucy0yMDI1XzUwNS5wZGY=",
    ),
}

EENADU = "https://www.eenadu.net/telangana/panchayat-elections-results-phase{p}/{d}"
EENADU_DISTRICTS = [
    "adilabad",
    "bhadradri-kothagudem",
    "hanumakonda",
    "jagtial",
    "jayashankar-bhupalpally",
    "jangaon",
    "rajanna-sircilla",
    "mahabubabad",
    "mahabubnagar",
    "mancherial",
    "medak",
    "mulugu",
    "nagarkurnool",
    "nalgonda",
    "narayanpet",
    "nirmal",
    "nizamabad",
    "peddapally",
    "rangareddy",
    "sangareddy",
    "wanaparthy",
    "siddipet",
    "suryapet",
    "vikarabad",
    "jogulamba-gadwala",
    "kamareddy",
    "karimnagar",
    "khammam",
    "kumurambheem-asifabad",
    "warangal",
    "yadadri-bhuvanagiri",
]


def main():
    session = requests.Session()
    for name, (ts, url) in SEC_ARCHIVED.items():
        fetch(
            WAYBACK.format(ts=ts, url=url),
            f"data/raw/2025/sec/{name}",
            "tsec.gov.in via web.archive.org",
            session=session,
            delay=4,
        )
    for phase in (1, 2, 3):
        for district in EENADU_DISTRICTS:
            fetch(
                EENADU.format(p=phase, d=district),
                f"data/raw/2025/eenadu/phase{phase}/{district}.html",
                "eenadu.net",
                session=session,
                delay=2,
            )


if __name__ == "__main__":
    main()
