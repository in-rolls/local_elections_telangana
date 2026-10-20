# Inferred winner sex

Neither source records a sarpanch's sex. `winner_woman_probability_{2019,2025}.parquet`
hold, per seat with a named winner, the probability that the winner is a woman,
inferred from the printed name by `make infer` (`infer/winner_sex.py`). Use it
averaged over seats to estimate a share of women; never as anyone's sex.

Inputs beside each probability: the name's first and last words, naampy's
scores on them, and the fixed female/male name-ending indicators. The combiner
is fit on recorded sex of Telangana assembly candidates (2014, 2018 Lok Dhaba;
2023 ECI; `data/raw/labels/`).

| Check | Result |
|---|---|
| Assembly candidates, 5-fold CV grouped by name word (4,986 names, 453 women) | AUC 0.982; 92.5% of women and 94.3% of men on the right side of 0.5 |
| Winners of women's seats (women by law) | mean 0.915 (2019), 0.909 (2025); 6% below 0.5 |
| Winners of open seats | mean 0.175 (2019), 0.158 (2025) |

The women's-seat winners below 0.5 are mostly men's names (e.g. "Mamidi Raju",
"Moheen Mohammed"): a man listed for a woman's seat, or a source error. They
are kept as scored. `MANIFEST.json` has the coefficients, calibration bands,
versions and input hashes.
