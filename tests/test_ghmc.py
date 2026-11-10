import json
from collections import Counter

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from local_elections_telangana.build import contract
from local_elections_telangana.parse import ghmc


def test_offline_release_and_page_break_regressions(tmp_path):
    outputs = ghmc.build(tmp_path)
    for name in outputs:
        table = pq.read_table(tmp_path / f"{name}.parquet")
        assert table.equals(pq.read_table(ghmc.RELEASE / f"{name}.parquet"))
        assert table.schema.equals(ghmc.arrow_schema(name))
        assert table.schema.field("ward_no").type == pa.string()
        for field in table.schema:
            if field.name.endswith("_woman"):
                assert field.type == pa.int8() and field.nullable
    first = outputs["candidates_2016"]
    assert len({(r["ward_no"], r["candidate_no"]) for r in first}) == 1333
    assert all(r.get("candidate_woman_raw") is None for r in first)
    assert Counter(r["ward_no"] for r in first if r["elected"]) == dict.fromkeys(
        map(str, range(1, 151)), 1
    )
    restored = [
        r for r in first if not json.loads(r["raw_record"])["name_from_numeric_line"]
    ]
    assert len(restored) == 29
    assert sum(r["elected"] for r in restored) == 4
    assert (
        next(r for r in restored if r["ward_no"] == "88" and r["elected"])[
            "candidate_name"
        ]
        == "Mohammed Akheel Ahmed"
    )
    assert next(r for r in restored if r["ward_no"] == "19")["candidate_name"] == (
        "Senapathy Jyotsna Alias Senapathy Archana"
    )
    for row in first:
        raw = json.loads(row["raw_record"])
        assert row["candidate_name"] == ghmc.normalize(raw["name_cell"])
        assert raw["result_line"] and len(raw["name_cell_bbox"]) == 4
    profiles = outputs["candidate_profiles_2020"]
    assert Counter(r["candidate_woman_raw"] for r in profiles) == {
        "Male": 582,
        "Female": 540,
    }
    assert all(r.get("elected") is None for r in profiles)
    assert all(r.get("votes") is None for r in profiles)
    returns = outputs["candidate_returns_2020"]
    assert len(returns) == 1117
    assert len({(r["ward_no"], r["candidate_no"]) for r in returns}) == 1117
    assert {r["ward_no"] for r in returns} == set(map(str, range(1, 151))) - {"136"}
    assert Counter(r["ward_no"] for r in returns if r["elected"]) == dict.fromkeys(
        set(map(str, range(1, 151))) - {"136"}, 1
    )
    assert (
        next(r for r in returns if r["candidate_name"] == "J. PRABHU DASS")["ward_no"]
        == "4"
    )
    assert (
        next(r for r in returns if r["candidate_name"] == "G ANURADHA")["ward_no"]
        == "137"
    )
    for r in returns:
        assert r["ward_link_basis"] == "unique_profile_ward_for_candidate_block"
        assert json.loads(r["raw_record"])[12]
    winners = [r for r in outputs["winners"] if r["year"] == 2020]
    assert sum(r["winner_woman"] for r in winners) == 81
    assert sum(r["reserved_woman"] for r in winners) == 75
    assert next(r for r in winners if r["ward_no"] == "150")["winner"] == (
        "Kontham Deepika"
    )
    assert next(r for r in winners if r["ward_no"] == "18")["winner"] == (
        "Akula Ramesh Goud"
    )
    assert next(r for r in winners if r["ward_no"] == "3")["winner_woman"] == 1
    assert next(r for r in winners if r["ward_no"] == "3")["reserved_woman"] == 0


def test_changed_source_hash_rejected(monkeypatch):
    monkeypatch.setattr(ghmc, "sha", lambda path: "changed")
    with pytest.raises(ValueError, match="Source bytes changed"):
        ghmc.verify_sources()


def test_unknown_reservation_and_duplicate_winner_rejected():
    with pytest.raises(ValueError, match="Unknown reservation"):
        ghmc.reservation("?")
    assert ghmc.reservation("SC (General)") == ("SC", 0)
    assert ghmc.reservation("Women (General)") == ("NONE", 1)
    with pytest.raises(ValueError, match="exactly one winner"):
        ghmc.validate([{"ward_no": 1, "elected": True}] * 2, 1)


def test_contract_rejects_boolean_woman(tmp_path, monkeypatch):
    name = "ghmc_candidate_profiles_2020"
    relative = contract.GHMC_TABLES[name]
    table = pq.read_table(contract.DATA / relative)
    column = table.schema.get_field_index("candidate_woman")
    table = table.set_column(
        column,
        pa.field("candidate_woman", pa.bool_()),
        pa.array([bool(v) for v in table.column(column).to_pylist()]),
    )
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    pq.write_table(table, path)
    monkeypatch.setattr(contract, "DATA", tmp_path)
    assert contract.failures(name)[0][1] == "exact_arrow_schema"


def test_all_urban_contracts_are_registered_and_valid():
    assert len(contract.GHMC_TABLES) == 4
    for name in contract.GHMC_TABLES:
        assert contract.failures(name) == []
