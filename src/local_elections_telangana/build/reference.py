"""Published figures the data are checked against, each with its source.

Nothing here is computed from the data. Where sources disagree, every figure is
kept, because which denominator is right is itself a finding.
"""

# Sarpanch posts / gram panchayats in the December 2025 election.
TOTALS_2025 = {
    "sec_phase_table_gps": {
        "value": 12733,
        "source": "TGSEC, '2nd Ordinary Elections to Rural Local Bodies, 2025, "
        "Gram Panchayat elections' phase-wise table (September 2025 schedule), "
        "data/raw/2025/sec/sec_phasewise_gp_elections_2025.pdf",
    },
    "gps_notified": {
        "value": 12735,
        "source": "Siasat, 'Over 25k candidates enter fray for Telangana's "
        "panchayat elections' (citing the SEC), https://www.siasat.com/"
        "over-25k-candidates-enter-fray-for-telanganas-panchayat-elections-3306765/",
    },
    "sarpanch_posts_notified": {
        "value": 12728,
        "source": "Same Siasat article; also South First, 'Telangana SEC "
        "announces gram panchayat poll schedule'.",
    },
    "gps_in_results_count": {
        "value": 12727,
        "source": "Siasat, 18 Dec 2025, 'Telangana panchayat polls: Congress "
        "wins over 53pc of all sarpanch posts', https://www.siasat.com/"
        "telangana-panchayat-polls-congress-wins-over-53pc-of-all-sarpanch-"
        "posts-3313500/",
    },
}

# Notification 1085/TGSEC-PR/2025 holds these back under court orders.
COURT_HELD_2025 = {"Mulugu": 25, "Karimnagar": 2, "Khammam": 5}

BC_2025 = {
    "seats": 2176,
    "of": 12735,
    "share": 0.1708,
    "source": "SEC figures reported by Siasat (article above) and South First, "
    "'Telangana gram panchayat polls: BC quota slashed to 17 percent', "
    "https://thesouthfirst.com/telangana/telangana-gram-panchayat-polls-bc-"
    "quota-slashed-to-17-percent-amidst-backlash-over-betrayal-of-promises/",
}

WOMEN_STATUTE = {
    "share": 0.50,
    "source": "Telangana Panchayat Raj Act 2018 and G.O.Ms.No.46 (22 Nov 2025): "
    "50% of seats in each category for women, rounded down where odd "
    "(South First, 'Telangana issues new reservation guidelines').",
}

# Backing-party tallies for all three phases. Gram panchayat polls are
# non-party; these are the newspaper's attributions, as is Eenadu's.
PARTY_2025 = {
    "counts": {"INC": 6822, "BRS": 3519, "BJP": 703, "OTH": 1654},
    "source": "Siasat, 18 Dec 2025 (article above): Congress-backed 6,822 "
    "(53.60%), BRS 3,519, BJP-backed 703, independents and others 1,654.",
}

TOTAL_2019 = {
    "value": 12728,
    "source": "TGSEC notification for the 2019 GP election, as reported: "
    "12,728 sarpanch posts across 12,751 GPs (local_elections, "
    "common/reference.py).",
}

# SEC phase table spelling -> the district names used in the data.
SEC_TABLE_NAMES = {
    "Narayanapet": "Narayanpet",
    "Janagaon": "Jangaon",
    "Jayashankar Bhupalapally": "Jayashankar Bhupalpally",
    "Vkarabad": "Vikarabad",
    "Ranga Reddy": "Rangareddy",
    "Yadadri": "Yadadri Bhuvanagiri",
    "Komaram Bheem Asifbad": "Komaram Bheem Asifabad",
    "Karimanagar": "Karimnagar",
    "Jagital": "Jagtial",
    "Rajanna sircilla": "Rajanna Sircilla",
}

WARDS_2019 = {
    "value": 112242,
    "source": "Ward-member seats in the 2019 GP election as recorded in "
    "in-rolls/local_elections (data/telangana readme, 'vs published').",
}
