"""Validate the published tables against their Table Schemas in schemas/.

The JSON files are the contract, readable by any Frictionless tool. Each field
also carries `arrowType`, the exact Arrow type the parquet stores. Checks run
through pandera, built from the same JSON, with two of its defaults off as in
in-rolls/local_elections (tools/contract.py): no coercion, which would turn
the text "1" into a number, and Arrow dtypes instead of numpy ones, which
cannot hold a null integer.

    python -m local_elections_telangana.build.contract
"""

import json
import sys

import pandas as pd
import pandera.pandas as pdx
import pyarrow as pa
import pyarrow.parquet as pq
from pandera.errors import SchemaErrors
from pandera.io.pandas_io import from_frictionless_schema

from local_elections_telangana.parse.common import DATA, ROOT

SCHEMAS = ROOT / "schemas"
# schema name -> published file
TABLES = {
    "2025_sarpanch_results": "release/2025/sarpanch_results.parquet",
    "2025_sarpanch_candidates": "release/2025/sarpanch_candidates.parquet",
    "2025_ward_results": "release/2025/ward_results.parquet",
}
ARROW = {
    "string": pa.string(),
    "bool": pa.bool_(),
    "int8": pa.int8(),
    "int16": pa.int16(),
    "int32": pa.int32(),
    "int64": pa.int64(),
}


def descriptor(name):
    return json.loads((SCHEMAS / f"{name}.json").read_text(encoding="utf-8"))


def schema(name):
    desc = descriptor(name)
    parsed = from_frictionless_schema(desc)
    columns = parsed.update_columns(
        {
            f["name"]: {
                "coerce": False,
                "dtype": pd.ArrowDtype(ARROW[f["arrowType"]]),
            }
            for f in desc["fields"]
        }
    ).columns
    return pdx.DataFrameSchema(
        columns,
        coerce=False,
        strict=True,
        ordered=True,
        # pandera does not read primaryKey from the descriptor
        unique=desc["primaryKey"],
        name=name,
    )


def load(path):
    table = pq.read_table(path)
    plain = []
    for f in table.schema:
        t = f.type.value_type if pa.types.is_dictionary(f.type) else f.type
        plain.append(
            pa.field(f.name, pa.string() if pa.types.is_large_string(t) else t)
        )
    return table.cast(pa.schema(plain)).to_pandas(types_mapper=pd.ArrowDtype)


def failures(name):
    """[(column, check, failing rows, example)] for one table; empty if valid."""
    frame = load(DATA / TABLES[name])
    try:
        schema(name).validate(frame, lazy=True)
    except SchemaErrors as errors:
        cases = errors.failure_cases
        out = []
        for (column, check), group in cases.groupby(
            ["column", "check"], dropna=False, sort=False
        ):
            example = group["failure_case"].iloc[0]
            if str(check).startswith("dtype("):
                example = str(frame[column].dtype) if column in frame else "missing"
            out.append((str(column), str(check), len(group), str(example)[:80]))
        return out
    return []


def main():
    bad = False
    for name in TABLES:
        found = failures(name)
        print(f"{name}: {'valid' if not found else f'{len(found)} failing checks'}")
        for row in found:
            print("   ", row)
        bad |= bool(found)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
