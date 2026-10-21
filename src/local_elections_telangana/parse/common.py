"""Shared vocabulary: the pooled schema's reservation fields and name folding."""

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"

# The commission's codes: caste category, then (G)eneral or (W)oman.
# UR is unreserved, which the pooled schema calls NONE.
CODE = re.compile(r"^(UR|SC|ST|BC)\s*\((G|W)\)$")
CASTE = {"UR": "NONE", "SC": "SC", "ST": "ST", "BC": "BC"}

SEAT_COLUMNS = [
    "state",
    "year",
    "district",
    "block",
    "gram_panchayat",
    "tier",
    "tier_local",
    "reserved_label",
    "reserved_caste",
    "reserved_woman",
    "reserved_raw",
    "winner",
    "winner_basis",
    "party",
    "unopposed",
    "script",
    "source_path",
    "source_url",
    "source_locator",
]


def reservation(code):
    """(reservation label, reserved_caste, reserved_woman) for a code."""
    got = CODE.match(code.strip())
    if not got:
        raise ValueError(f"unknown reservation code {code!r}")
    caste, gender = CASTE[got.group(1)], got.group(2)
    woman = int(gender == "W")
    stem = "" if caste == "NONE" else f"{caste} "
    return f"{stem}{'Woman' if woman else 'Other than Woman'}", caste, woman


def fold(name):
    """Lower-case Latin name with punctuation, spaces and case removed."""
    text = unicodedata.normalize("NFKC", str(name)).lower()
    return re.sub(r"[^a-z0-9]", "", text)
