"""Parse raw connector extracts (TOON format) into a tidy EV production CSV.

The connector returns results in a compact "TOON" block:

    [<n>]{col,col,...}:
      val,val,...

Large results are written to disk by the client rather than returned inline;
those files are JSON arrays of {type, text} objects. This script reads either
shape, concatenates the rows, drops non-EV false positives, de-duplicates and
writes a single tidy CSV.

Usage:
    python scripts/parse_production_extract.py data/raw/*.txt -o data/processed/ev_production_model_monthly.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Sub-segments that the source classifies as electric outright.
ELECTRIC_SUB_SEGMENTS = {
    "AE1: Upto 250 W Electric",
    "AE2: >250 W Electric",
    "E-Cart",
    "E-Rickshaw",
}

# Word-boundary anchored so "Bonneville" does not match on "ev".
EV_MODEL_RE = re.compile(r"(?i)(\bEV\b|EV$|\bElectric\b|\be-)")

KEY_FIELDS = ("month", "category", "segment", "sub_segment", "oem", "model")
NUMERIC_FIELDS = ("production_units", "domestic_sales_units", "export_units")

COLUMN_RENAMES = {
    "Category_Clean": "category",
    "Segment_Clean": "segment",
    "Sub_Segment_Clean": "sub_segment",
    "OEM_Clean": "oem",
    "Model": "model",
}


def load_text(path: Path) -> str:
    """Return the payload text, whether the file is raw text or a JSON envelope."""
    body = path.read_text()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body
    if isinstance(payload, list):
        return "\n".join(part.get("text", "") for part in payload if isinstance(part, dict))
    return body


def parse_toon(text: str) -> list[dict[str, str]]:
    """Extract rows from the TOON block in `text`."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        header = re.match(r"^\[(\d+)\]\{(.+?)\}:\s*$", line)
        if header:
            break
    else:
        return []

    columns = [COLUMN_RENAMES.get(c.strip(), c.strip()) for c in header.group(2).split(",")]
    rows: list[dict[str, str]] = []

    # Data rows are the indented lines following the header.
    for line in lines[index + 1:]:
        if not line.startswith("  "):
            break
        values = [v.strip() for v in line.strip().split(",")]
        if len(values) != len(columns):
            # A comma inside a model name would desynchronise the row; skip it
            # rather than silently mis-assigning columns.
            print(f"  ! skipping malformed row: {line.strip()!r}", file=sys.stderr)
            continue
        rows.append(dict(zip(columns, values)))

    declared = int(header.group(1))
    if len(rows) != declared:
        print(f"  ! expected {declared} rows, parsed {len(rows)}", file=sys.stderr)
    return rows


def is_ev(row: dict[str, str]) -> bool:
    if row.get("sub_segment") in ELECTRIC_SUB_SEGMENTS:
        return True
    return bool(EV_MODEL_RE.search(row.get("model", "")))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path, help="raw extract files")
    ap.add_argument("-o", "--output", required=True, type=Path)
    args = ap.parse_args()

    # Later files win on key collisions, so pass targeted re-pulls last.
    merged: dict[tuple[str, ...], dict[str, str]] = {}
    dropped = 0

    for path in sorted(args.inputs):
        rows = parse_toon(load_text(path))
        kept = 0
        for row in rows:
            if not is_ev(row):
                dropped += 1
                continue
            merged[tuple(row[f] for f in KEY_FIELDS)] = row
            kept += 1
        print(f"{path.name}: parsed {len(rows)}, kept {kept}")

    records = [merged[k] for k in sorted(merged)]
    for rec in records:
        for field in NUMERIC_FIELDS:
            # The source leaves the metric blank when a model reports nothing
            # that month; keep that distinct from a reported zero.
            rec[field] = rec.get(field, "") or ""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*KEY_FIELDS, *NUMERIC_FIELDS])
        writer.writeheader()
        writer.writerows(records)

    months = sorted({r["month"] for r in records})
    print(
        f"\nwrote {len(records)} rows to {args.output} "
        f"({months[0]} to {months[-1]}); dropped {dropped} non-EV rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
