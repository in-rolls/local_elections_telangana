"""Link 2019 sarpanch seats to 2025 sarpanch seats, precision first.

The analysis compares seats with and without a 2019 women's quota on who wins
in 2025. A wrong link adds noise and can bias that comparison; a missing link
only costs sample. So a doubtful pair is left unlinked.

Two routes that share no code:

- By code. The commission keeps its district, mandal and GP codes across
  elections. 2025 seats carry them (parse/y2025_sec.py); 2019 seats get them
  from the open-data candidate table, joined on (district, mandal, GP) names
  where that key is unique in both 2019 tables. A code pair counts only if
  the names also agree (qualifiers equal, similarity >= CODE_NAME_FLOOR), so
  a code reused for a different GP cannot link.
- By name. preclink inside district groups that absorb the 2019 and 2021
  reorganisations, without mandals or codes: name similarity with qualifier
  vetoes, preclink's margin filter (a 2019 GP whose best and second-best
  2025 candidates score within MARGIN is dropped), then the Hungarian
  one-to-one assignment.

Decision. A pair both routes make is linked. A pair only one route makes is
linked when the other route makes no claim on either GP. A pair the routes
dispute (each links one of the GPs elsewhere) is dropped and written to
conflicts_2019_2025.csv. The name route's precision is measured against the
code route on GPs both cover, by score band; NAME_THRESHOLD comes from that.

Names. Lower case, HTML entities decoded, list serials ("10)Kannaigudem")
and "(proposed gp)"/"(hq)" notes dropped, then the spelling variants English
renderings of Telugu names drift between (release.loose). Qualifiers must
agree on both sides, and one stated on one side only vetoes:
  letter      Pardi (B) / Pardi (K); Gokhul (T)
  number      Singavaram-1 / -2; Battu Thanda -2
  size        pedda/big/kalan/buzurg vs chinna/small/khurd/kurd
  age         kotha/new vs patha/old
  kind        thanda/tanda, colony, camp

Not used: reservation and winners (the analysis variables). Winners are used
only by the check: the share of linked seats whose winner's name recurs,
against random pairs in the same district group.

    python -m local_elections_telangana.linkage.gp_links
"""

import hashlib
import html
import json
import re
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from preclink import Pipeline
from rapidfuzz import fuzz

from local_elections_telangana.build.release import GROUP, RENAMED_2019, loose
from local_elections_telangana.parse.common import DATA, fold

OUT = DATA / "linkage"
SOURCES = {
    "seats_2019": DATA / "2019/sarpanch_results.parquet",
    "candidates_2019": DATA / "2019/sarpanch_candidates.parquet",
    "seats_2025": DATA / "2025/sarpanch_results.parquet",
}
# Districts carved out in 2019 are filed under their parents in the 2019
# listing; group them with the parent.
GROUPS = {**GROUP, "Hanumakonda": "Warangal+Hanumakonda"}

# Set from the agreement with the code route (MANIFEST.json, name_route_bands):
# pairs scoring 0.95+ agree with it 99.98% of the time (9,464 judged), 0.85-0.95
# only 95-96%, and the disagreements read by hand were the name route jumping
# to a similar name in another mandal, which it cannot see.
NAME_THRESHOLD = 0.95
CODE_NAME_FLOOR = 0.80
MARGIN = 0.05

LETTER = re.compile(r"(?:\(\s*([a-z]{1,2})\s*\)|[\s\-]([a-z])\.?)\s*$")
NUMBER = re.compile(r"(?:[\s\-(]|^)(\d{1,2}|i{1,3}|iv)\s*\)?\s*$")
SERIAL = re.compile(r"^\s*\d{1,2}\s*\)\s*")
NOTES = re.compile(r"\((?:proposed gp|new hq|hq|r&r colony|r&r)\)")
WORDS = {
    "size": {
        "pedda": "big",
        "big": "big",
        "kalan": "big",
        "buzurg": "big",
        "chinna": "small",
        "small": "small",
        "khurd": "small",
        "kurd": "small",
    },
    "age": {"kotha": "new", "new": "new", "patha": "old", "old": "old"},
    "kind": {"thanda": "thanda", "tanda": "thanda", "colony": "colony", "camp": "camp"},
}


def clean(name):
    text = html.unescape(str(name)).lower().strip()
    text = SERIAL.sub("", text)
    return re.sub(r"\s+", " ", NOTES.sub(" ", text)).strip(" -.")


def tokens(text):
    return [t for t in re.split(r"[\s\-()./]+", text) if t]


def qualifiers(text):
    found = {}
    number = NUMBER.search(text)
    if number:
        found["number"] = number.group(1)
        text = text[: number.start()]
    letter = LETTER.search(text)
    if letter:
        found["letter"] = letter.group(1) or letter.group(2)
    for family, words in WORDS.items():
        hits = {words[t] for t in tokens(text) if t in words}
        if hits:
            found[family] = "+".join(sorted(hits))
    return found


def core(text):
    """The name with its qualifiers removed, folded loosely."""
    text = NUMBER.sub(" ", text)
    text = LETTER.sub(" ", text)
    every = {w for words in WORDS.values() for w in words}
    return loose(" ".join(t for t in tokens(text) if t not in every))


def similarity(a, b):
    if not a or not b:
        return 0.0
    return fuzz.ratio(a, b) / 100


def name_score(a, qa, b, qb, threshold):
    if qa != qb:
        return 0.0
    score = similarity(a, b)
    return score if score >= threshold else 0.0


@dataclass(frozen=True, slots=True)
class PlaceName:
    """preclink comparison on (core name, qualifiers)."""

    column: str = "name_key"
    weight: float = 1.0
    threshold: float = NAME_THRESHOLD

    def compare(self, left, right):
        return pd.Series(
            [
                name_score(a, qa, b, qb, self.threshold)
                for (a, qa), (b, qb) in zip(left, right, strict=True)
            ],
            index=left.index,
        )


def prepare(frame, year):
    frame = frame.copy()
    frame["group"] = frame["district"].map(lambda d: GROUPS.get(d, d))
    frame["name_clean"] = frame["gram_panchayat"].map(clean)
    frame["qualifiers"] = frame["name_clean"].map(qualifiers)
    frame["name_core"] = frame["name_clean"].map(core)
    frame["qkey"] = frame["qualifiers"].map(lambda q: json.dumps(q, sort_keys=True))
    frame["name_key"] = list(zip(frame["name_core"], frame["qualifiers"], strict=True))
    frame["year"] = year
    return frame


def codes_2019(seats):
    """SEC code key for each 2019 seat, via the open-data candidate table."""
    cands = pd.read_parquet(SOURCES["candidates_2019"])
    cands["district"] = cands["district"].replace(RENAMED_2019)
    gps = cands.drop_duplicates(["district_id", "mandal_id", "gp_code"])
    gps = gps.assign(
        k=gps["district"].map(fold)
        + "|"
        + gps["block"].map(fold)
        + "|"
        + gps["gram_panchayat"].map(fold),
        code=gps["district_id"].astype(int).astype(str)
        + "|"
        + gps["mandal_id"].astype(int).astype(str)
        + "|"
        + gps["gp_code"].astype(int).astype(str),
    ).drop_duplicates("k", keep=False)
    k = (
        seats["district"].map(fold)
        + "|"
        + seats["block"].map(fold)
        + "|"
        + seats["gram_panchayat"].map(fold)
    )
    unique = ~k.duplicated(keep=False)
    return k.map(gps.set_index("k")["code"]).where(unique)


def code_route(left, right):
    r = right.reset_index(names="right_index")
    pairs = left.reset_index(names="left_index").dropna(subset=["code"])
    pairs = pairs.merge(r, on="code", suffixes=("_l", "_r"))
    pairs["code_name_score"] = [
        name_score(a, qa, b, qb, CODE_NAME_FLOOR)
        for (a, qa), (b, qb) in zip(
            pairs["name_key_l"], pairs["name_key_r"], strict=True
        )
    ]
    rejected = int((pairs["code_name_score"] == 0).sum())
    pairs = pairs[pairs["code_name_score"] > 0]
    return pairs[["left_index", "right_index", "code_name_score"]], rejected


def name_route(left, right, threshold):
    usable_l = left[~left.duplicated(["group", "name_core", "qkey"], keep=False)]
    usable_r = right[~right.duplicated(["group", "name_core", "qkey"], keep=False)]
    pipeline = (
        Pipeline()
        .block(on="group")
        .score(comparisons=[PlaceName(threshold=threshold)])
        .filter(min_score=threshold, margin=MARGIN)
        .decide(method="hungarian")
        .build()
    )
    cols = ["group", "name_key"]
    got = pipeline.link(usable_l[cols], usable_r[cols]).matches
    excluded = {
        "2019_name_repeated_in_group": int(len(left) - len(usable_l)),
        "2025_name_repeated_in_group": int(len(right) - len(usable_r)),
    }
    return got[["left_index", "right_index", "score"]], excluded


def bands(name_pairs, code_pairs):
    """Name-route agreement with the code route, by score band, on 2019 GPs
    the code route links."""
    truth = code_pairs.set_index("left_index")["right_index"]
    judged = name_pairs[name_pairs["left_index"].isin(truth.index)].copy()
    judged["agrees"] = (
        judged["right_index"].to_numpy()
        == truth.reindex(judged["left_index"]).to_numpy()
    )
    edges = [0.75, 0.80, 0.85, 0.90, 0.95, 1.0001]
    judged["band"] = pd.cut(judged["score"], edges, right=False).astype(str)
    out = judged.groupby("band", observed=True)["agrees"].agg(["size", "mean"])
    return {
        b: {"judged": int(r["size"]), "agree": round(float(r["mean"]), 4)}
        for b, r in out.iterrows()
    }


def decide(name_pairs, code_pairs):
    n = {
        (a, b)
        for a, b in zip(name_pairs.left_index, name_pairs.right_index, strict=True)
    }
    c = {
        (a, b)
        for a, b in zip(code_pairs.left_index, code_pairs.right_index, strict=True)
    }
    n_left = {a for a, _ in n}
    n_right = {b for _, b in n}
    c_left = {a for a, _ in c}
    c_right = {b for _, b in c}
    rows, conflicts = [], []
    for a, b in n | c:
        if (a, b) in n and (a, b) in c:
            rows.append((a, b, "code_and_name"))
        elif (a, b) in n:
            if a in c_left or b in c_right:
                conflicts.append((a, b, "name"))
            else:
                rows.append((a, b, "name_only"))
        elif a in n_left or b in n_right:
            conflicts.append((a, b, "code"))
        else:
            rows.append((a, b, "code_only"))
    return rows, conflicts


def winners_share(a, b):
    fa, fb = a.map(lambda x: loose(str(x))), b.map(lambda x: loose(str(x)))
    return np.array(
        [
            bool(x) and bool(y) and fuzz.token_sort_ratio(x, y) >= 90
            for x, y in zip(fa, fb, strict=True)
        ]
    )


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(threshold=NAME_THRESHOLD, probe=0.75):
    s19 = prepare(pd.read_parquet(SOURCES["seats_2019"]), 2019)
    s25 = prepare(pd.read_parquet(SOURCES["seats_2025"]), 2025)
    s19["code"] = codes_2019(s19)
    s25["code"] = (
        s25["district_id"].astype(int).astype(str)
        + "|"
        + s25["mandal_id"].astype(int).astype(str)
        + "|"
        + s25["gp_code"].astype(int).astype(str)
    )
    code_pairs, code_rejected = code_route(s19, s25)
    probe_pairs, _ = name_route(s19, s25, probe)
    name_pairs, excluded = name_route(s19, s25, threshold)
    rows, conflicts = decide(name_pairs, code_pairs)

    links = pd.DataFrame(rows, columns=["i19", "i25", "link_basis"])
    a, b = (
        s19.loc[links["i19"]].reset_index(drop=True),
        s25.loc[links["i25"]].reset_index(drop=True),
    )
    name_score_of = name_pairs.set_index(["left_index", "right_index"])["score"]
    table = pd.DataFrame(
        {
            "district_2019": a["district"],
            "block_2019": a["block"],
            "gram_panchayat_2019": a["gram_panchayat"],
            "source_locator_2019": a["source_locator"],
            "sec_code_2019": a["code"],
            "district_2025": b["district"],
            "block_2025": b["block"],
            "gram_panchayat_2025": b["gram_panchayat"],
            "district_id_2025": b["district_id"],
            "mandal_id_2025": b["mandal_id"],
            "gp_code_2025": b["gp_code"],
            "source_path_2025": b["source_path"],
            "source_locator_2025": b["source_locator"],
            "district_group": a["group"],
            "link_basis": links["link_basis"],
            "name_score": [
                name_score_of.get((i, j), np.nan)
                for i, j in zip(links["i19"], links["i25"], strict=True)
            ],
            "qualifiers": a["qkey"],
        }
    )
    code_score_of = code_pairs.set_index(["left_index", "right_index"])[
        "code_name_score"
    ]
    table["code_name_score"] = [
        code_score_of.get((i, j), np.nan)
        for i, j in zip(links["i19"], links["i25"], strict=True)
    ]
    table["name_score"] = table["name_score"].astype("float64")
    table["winner_name_shared"] = winners_share(a["winner"], b["winner"])
    rng = np.random.default_rng(20192025)
    shuffled = b.groupby(a["group"].to_numpy())["winner"].transform(
        lambda s: s.iloc[rng.permutation(len(s))].to_numpy()
    )
    random_shared = winners_share(a["winner"], shuffled)
    table = table.sort_values(["district_2019", "block_2019", "gram_panchayat_2019"])
    table = table.reset_index(drop=True)

    conf = pd.DataFrame(conflicts, columns=["i19", "i25", "route"])
    conf_table = pd.DataFrame(
        {
            "route": conf["route"],
            "district_2019": s19.loc[conf["i19"], "district"].to_numpy(),
            "block_2019": s19.loc[conf["i19"], "block"].to_numpy(),
            "gram_panchayat_2019": s19.loc[conf["i19"], "gram_panchayat"].to_numpy(),
            "block_2025": s25.loc[conf["i25"], "block"].to_numpy(),
            "gram_panchayat_2025": s25.loc[conf["i25"], "gram_panchayat"].to_numpy(),
            "gp_code_2025": s25.loc[conf["i25"], "gp_code"].to_numpy(),
        }
    ).sort_values(["district_2019", "block_2019", "gram_panchayat_2019"])

    basis = table["link_basis"].value_counts().to_dict()
    summary = {
        "seats_2019": len(s19),
        "seats_2025": len(s25),
        "linked": len(table),
        "by_basis": {k: int(v) for k, v in basis.items()},
        "conflicts_dropped": len(conf_table),
        "code_route": {
            "seats_2019_with_code": int(s19["code"].notna().sum()),
            "pairs": len(code_pairs),
            "code_matches_rejected_for_name": code_rejected,
        },
        "name_route": {"pairs": len(name_pairs), **excluded},
        "name_route_bands": bands(probe_pairs, code_pairs),
        "routes_agree_where_both_link_the_2019_gp": round(
            float(
                np.mean(
                    [
                        r == code_pairs.set_index("left_index")["right_index"].get(i)
                        for i, r in zip(
                            name_pairs.left_index, name_pairs.right_index, strict=True
                        )
                        if i in set(code_pairs.left_index)
                    ]
                )
            ),
            4,
        ),
        "winner_name_shared": {
            "linked": round(float(table["winner_name_shared"].mean()), 4),
            **{
                k: round(float(g["winner_name_shared"].mean()), 4)
                for k, g in table.groupby("link_basis")
            },
            "random_pairs_in_group": round(float(random_shared.mean()), 4),
        },
    }
    return table, conf_table, summary


def main():
    table, conflicts, summary = build()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "gp_2019_2025.parquet"
    table.to_parquet(path, index=False)
    conflicts.to_csv(OUT / "conflicts_2019_2025.csv", index=False)
    manifest = {
        "purpose": "2019 to 2025 sarpanch seat links, precision first. A link "
        "states that the commission's code and/or the GP name agree, not that "
        "boundaries are unchanged.",
        "matcher": {
            "preclink": version("preclink"),
            "rapidfuzz": version("rapidfuzz"),
            "name_threshold": NAME_THRESHOLD,
            "code_name_floor": CODE_NAME_FLOOR,
            "margin": MARGIN,
        },
        "inputs": {str(p.relative_to(DATA.parent)): sha(p) for p in SOURCES.values()},
        "code_sha256": sha(__file__),
        "output": {"path": path.name, "rows": len(table), "sha256": sha(path)},
        "summary": summary,
    }
    (OUT / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    )
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
