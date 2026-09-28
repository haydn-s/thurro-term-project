"""Convert a saved connector result (JSON-wrapped TOON) into CSV.

Large connector results are written to disk by the MCP layer instead of being
returned inline. They arrive as [{"type": ..., "text": ...}] where the text is a
header block followed by a TOON table:

    [N]{col,col,...}:
      val,val,...

The rows are CSV with a two-space indent, so they parse with the csv module
once the indent is stripped.
"""
import csv
import json
import re
import sys


def extract(path):
    with open(path) as fh:
        payload = json.load(fh)
    text = "\n".join(
        part["text"] for part in payload if isinstance(part, dict) and "text" in part
    )

    header = re.search(r"^\[(\d+)\]\{(.+?)\}:$", text, re.M)
    if not header:
        raise SystemExit(f"{path}: no TOON header found")
    declared = int(header.group(1))
    columns = next(csv.reader([header.group(2)]))

    body = text[header.end():].splitlines()
    rows = []
    for line in body:
        if not line.strip():
            continue  # blank remainder of the header line, or padding
        if not line.startswith("  "):
            break  # trailing COLUMNS/feedback footer
        rows.append(next(csv.reader([line[2:]])))

    if len(rows) != declared:
        raise SystemExit(f"{path}: declared {declared} rows, parsed {len(rows)}")
    bad = [r for r in rows if len(r) != len(columns)]
    if bad:
        raise SystemExit(f"{path}: {len(bad)} rows do not match {len(columns)} columns")
    return columns, rows


def main():
    if len(sys.argv) < 3:
        raise SystemExit("usage: toon_to_csv.py OUT.csv IN.txt [IN.txt ...]")
    out, inputs = sys.argv[1], sys.argv[2:]

    columns = None
    merged = []
    for path in inputs:
        cols, rows = extract(path)
        if columns is None:
            columns = cols
        elif cols != columns:
            raise SystemExit(f"{path}: column mismatch {cols} != {columns}")
        merged.extend(rows)

    # Columns named with a leading underscore are query padding, not data. They
    # exist only to widen rows enough that the connector spills the result to a
    # file instead of returning it inline; see data/README.md.
    keep = [i for i, name in enumerate(columns) if not name.startswith("_")]

    with open(out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([columns[i] for i in keep])
        writer.writerows([[row[i] for i in keep] for row in merged])
    print(f"{out}: {len(merged)} rows x {len(keep)} cols")


if __name__ == "__main__":
    main()
