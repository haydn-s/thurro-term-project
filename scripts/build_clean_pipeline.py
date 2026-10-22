"""Run the full panel build from clean data to model data.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import clean
import features


def main():
    print("=" * 60)
    print("STEP 1 / 2  Clean")
    print("=" * 60)
    clean.main()
    print()
    print("=" * 60)
    print("STEP 2 / 2  Features")
    print("=" * 60)
    features.main()
    print()
    print("Pipeline complete.")
    print(f"  Clean inputs:     data/clean/    (4 files)")
    print(f"  Modelling panels: data/model/    (2 files)")


if __name__ == "__main__":
    main()
