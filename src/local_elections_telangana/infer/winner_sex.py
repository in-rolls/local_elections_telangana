"""Inferred probability that an elected sarpanch is a woman.

Neither the 2019 listing nor the 2025 reports record the winner's sex, so it is
inferred from the printed Latin-script name and kept apart from the seat
tables in data/inferred/. This follows the `name-sex-inference` recipe and the
pooled dictionary's column names. A probability is for averaging over seats,
never a label for anyone.

Evidence, combined by a logistic regression:

- naampy's first-name score on the name's first and last words (Telangana
  names put the surname first as often as last: "Kumaram Vandana",
  "Santhoshi Poreddy"), and the highest and lowest score over every word
  (a woman's given name is often in the middle, before her husband's:
  "Banoth Sangitha Mahesh");
- fixed name endings, set from the standard markers in the spellings these
  names use: female -amma, -avva, bai, devi, rani, kumari, begum, bee;
  male -aiah, -ayya, -appa, -ulu, rao, raju, kumar, swamy, babu. (-anna is
  left out: it ends female names too, Prasanna and Thamanna.)
  Shared surnames (reddy, goud, naik) are left to naampy.

Labels are recorded sex: Telangana assembly candidates of 2014, 2018 (Lok
Dhaba) and 2023 (ECI), in the same state and script. Their women are few and
their names more formal than a village head's, so they fit only the
six-coefficient combiner; the scores themselves come from naampy and the fixed
endings, which were not fit on them. Women's-seat winners, who must be women,
measure recall on the target names.

    python -m local_elections_telangana.infer.winner_sex
"""

import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from naampy import estimate_first_name_pattern
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from local_elections_telangana.parse.common import DATA

OUT = DATA / "inferred"
SEATS = {year: DATA / f"{year}/sarpanch_results.parquet" for year in (2019, 2025)}
LABELS = {
    "data/raw/labels/lokdhaba_telangana_ae_2014.csv": ("Candidate", "Sex"),
    "data/raw/labels/lokdhaba_telangana_ae_2018.csv": ("Candidate", "Sex"),
    "data/raw/labels/eci_telangana_ae_2023_detailed_results.xlsx": (
        "CANDIDATE NAME",
        "SEX",
    ),
}
TITLES = {"smt", "sri", "shri", "dr", "mr", "mrs", "km", "kum", "late", "adv"}
FEMALE_WORDS = {"bai", "devi", "rani", "kumari", "begum", "bee", "bi"}
FEMALE_ENDINGS = ("amma", "avva", "bai")
MALE_WORDS = {"rao", "raju", "kumar", "swamy", "babu"}
MALE_ENDINGS = ("aiah", "ayya", "appa", "ulu")
FEATURES = [
    "logit_max",
    "logit_min",
    "logit_first",
    "logit_last",
    "abstain_first",
    "abstain_last",
    "female",
    "male",
]
P = "winner_female_probability_from_name"


def words(name):
    text = re.sub(r"^\s*\d+\s*", "", str(name).lower())
    return [t for t in re.split(r"[^a-z]+", text) if len(t) > 1 and t not in TITLES]


def markers(tokens):
    female = any(t in FEMALE_WORDS or t.endswith(FEMALE_ENDINGS) for t in tokens)
    male = any(t in MALE_WORDS or t.endswith(MALE_ENDINGS) for t in tokens)
    return int(female), int(male)


def naampy_scores(tokens):
    got = estimate_first_name_pattern(sorted(set(tokens)))
    return dict(zip(got["input_name"], got["female_label_score"], strict=True)), got


def features(names):
    frame = pd.DataFrame({"name": names})
    frame["words"] = frame["name"].map(words)
    frame["first_word"] = frame["words"].map(lambda w: w[0] if w else None)
    frame["last_word"] = frame["words"].map(lambda w: w[-1] if len(w) > 1 else None)
    every = [t for w in frame["words"] for t in w]
    score, raw = naampy_scores(every)

    def logit(p):
        q = min(max(p, 0.01), 0.99)
        return float(np.log(q / (1 - q)))

    scored = frame["words"].map(
        lambda w: [logit(score[t]) for t in w if pd.notna(score.get(t))]
    )
    frame["logit_max"] = scored.map(lambda v: max(v) if v else 0.0)
    frame["logit_min"] = scored.map(lambda v: min(v) if v else 0.0)
    for side in ("first", "last"):
        p = pd.to_numeric(frame[f"{side}_word"].map(score), errors="coerce").astype(
            "float64"
        )
        frame[f"naampy_{side}"] = p
        frame[f"abstain_{side}"] = p.isna().astype(int)
        q = p.fillna(0.5).clip(0.01, 0.99)
        frame[f"logit_{side}"] = np.log(q / (1 - q))
    marks = frame["words"].map(markers)
    frame["female"] = [m[0] for m in marks]
    frame["male"] = [m[1] for m in marks]
    return frame, raw


def labelled():
    rows = []
    for rel, (name, sex) in LABELS.items():
        path = DATA.parent / rel
        if path.suffix == ".xlsx":
            d = pd.read_excel(path, header=3)
        else:
            d = pd.read_csv(path)
        d = d[[name, sex]].dropna()
        d.columns = ["name", "sex"]
        d["sex"] = d["sex"].astype(str).str.upper().str[0]
        d = d[d["sex"].isin(["F", "M"]) & ~d["name"].str.contains("nota", case=False)]
        rows.append(d.assign(source=rel))
    out = pd.concat(rows)
    out["key"] = out["name"].map(lambda n: " ".join(words(n)))
    out = out[out["key"] != ""].drop_duplicates("key")
    out["y"] = (out["sex"] == "F").astype(int)
    return out.reset_index(drop=True)


def model():
    return LogisticRegression(class_weight="balanced", max_iter=1000)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    lab = labelled()
    lab_x, _ = features(lab["name"].tolist())
    groups = lab_x["last_word"].fillna(lab_x["first_word"]).fillna("")
    cv = np.zeros(len(lab))
    for train, test in GroupKFold(n_splits=5).split(lab_x, lab["y"], groups):
        fit = model().fit(lab_x.loc[train, FEATURES], lab["y"][train])
        cv[test] = fit.predict_proba(lab_x.loc[test, FEATURES])[:, 1]
    combiner = model().fit(lab_x[FEATURES], lab["y"])

    OUT.mkdir(parents=True, exist_ok=True)
    method = (
        f"logit(naampy {version('naampy')} on first and last word + fixed endings) "
        "fit on Telangana assembly candidates 2014/2018/2023 recorded sex"
    )
    target = {}
    for year, path in SEATS.items():
        seats = pd.read_parquet(path)
        keep = seats["winner"].notna()
        x, raw = features(seats.loc[keep, "winner"].tolist())
        p = combiner.predict_proba(x[FEATURES])[:, 1]
        out = seats.loc[
            keep,
            [
                "district",
                "block",
                "gram_panchayat",
                "woman_reserved",
                "caste_reservation",
                "winner",
                "source_path",
                "source_locator",
            ],
        ].reset_index(drop=True)
        out = pd.concat(
            [
                out,
                x[["first_word", "last_word", "naampy_first", "naampy_last"]],
                x[["female", "male"]].rename(
                    columns={"female": "female_marker", "male": "male_marker"}
                ),
            ],
            axis=1,
        )
        out[P] = p
        out["winner_female_probability_method"] = method
        out.to_parquet(OUT / f"winner_female_probability_{year}.parquet", index=False)
        women = out[out["woman_reserved"] == 1]
        open_ = out[out["woman_reserved"] == 0]
        target[str(year)] = {
            "winners_scored": len(out),
            "womens_seat_mean": round(float(women[P].mean()), 4),
            "womens_seat_below_half": round(float((women[P] < 0.5).mean()), 4),
            "open_seat_mean": round(float(open_[P].mean()), 4),
            "both_words_abstained": round(
                float((x["abstain_first"] & x["abstain_last"]).mean()), 4
            ),
            "naampy_model_revision": str(raw["model_revision"].iloc[0]),
        }

    labels = {
        "names": len(lab),
        "women": int(lab["y"].sum()),
        "cv_auc": round(float(roc_auc_score(lab["y"], cv)), 4),
        "cv_accuracy_women": round(float((cv[lab["y"] == 1] >= 0.5).mean()), 4),
        "cv_accuracy_men": round(float((cv[lab["y"] == 0] < 0.5).mean()), 4),
    }
    bands = pd.cut(cv, [0, 0.2, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
    calibration = (
        pd.DataFrame({"band": bands.astype(str), "y": lab["y"], "p": cv})
        .groupby("band")
        .agg(n=("y", "size"), predicted=("p", "mean"), observed=("y", "mean"))
        .round(4)
        .reset_index()
        .to_dict("records")
    )
    manifest = {
        "method": method,
        "features": FEATURES,
        "coefficients": dict(
            zip(FEATURES, combiner.coef_[0].round(4).tolist(), strict=True)
        ),
        "intercept": round(float(combiner.intercept_[0]), 4),
        "labels": labels,
        "label_calibration_cv": calibration,
        "target": target,
        "versions": {p: version(p) for p in ("naampy", "scikit-learn", "pandas")},
        "inputs": {
            **{rel: sha(DATA.parent / rel) for rel in LABELS},
            **{str(p.relative_to(DATA.parent)): sha(p) for p in SEATS.values()},
        },
        "code_sha256": sha(__file__),
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(
        json.dumps(
            {k: manifest[k] for k in ("coefficients", "labels", "target")}, indent=1
        )
    )


if __name__ == "__main__":
    main()
