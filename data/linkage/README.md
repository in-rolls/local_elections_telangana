# 2019 → 2025 sarpanch seat links

`gp_2019_2025.parquet`: one row per linked pair of a 2019 seat
(`2019/sarpanch_results.parquet`, by `source_locator_2019`) and a 2025 seat
(`2025/sarpanch_results.parquet`, by `source_path_2025` + `source_locator_2025`).
Built by `make link` (`linkage/gp_links.py`); `MANIFEST.json` holds the input
hashes, settings and every number below.

Two routes that share no code, both precision first:

- **Code.** The State Election Commission keeps its district, mandal and GP
  codes across elections. 2025 seats carry them; 2019 seats get them from the
  open-data candidate table. A code pair counts only if the names also agree
  (qualifiers equal, similarity ≥ 0.80): 285 code matches were rejected for
  their names.
- **Name.** preclink inside district groups (no mandals, no codes): name
  similarity with qualifier vetoes (letter, number, pedda/chinna, kotha/patha,
  thanda/colony/camp), a 0.05 margin filter, then a one-to-one assignment.

| `link_basis` | Pairs | Meaning |
|---|---:|---|
| `code_and_name` | 9,463 | both routes make this pair |
| `code_only` | 1,647 | code pair; the name route makes no claim on either GP (mostly names repeated in the district, which it excludes) |
| `name_only` | 354 | name pair scoring ≥ 0.95; no code pair for either GP (mostly GPs moved into mandals created after 2019, which got new codes) |

11,464 of 12,018 2019 seats are linked. 9 pairs the routes dispute are
dropped and listed in `conflicts_2019_2025.csv`.

**How good.** Where both routes link a 2019 GP, they choose the same 2025 GP
99.9% of the time. The name route's agreement with the code route by score
band set its threshold: 99.98% at 0.95 and above (9,464 pairs judged),
95-96% between 0.85 and 0.95, where the misses read by hand were names
jumping to a similar GP in another mandal. Same winner's name in both years:
1.0% of linked seats against 0.01% of random pairs in the same district group.

**Rotation on the links.** 92% of 2019 women's seats are open in 2025 and
83% of 2019 open seats are women's seats in 2025. 954 seats are open in both
elections with a declared 2025 result.
