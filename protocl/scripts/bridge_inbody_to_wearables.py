"""Bridge InBody weight + body fat % into wearables.csv.

Adds two columns to wearables.csv:
  - weight_lbs       (from inbody.csv, only on scan dates — no interpolation)
  - body_fat_pct     (from inbody.csv, same)

This is the cheapest possible way to surface weight trend in the dashboard
without waiting for an Apple Health export.zip backfill.

Re-runnable. Safe to call after every InBody scan.
"""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data" / "ryan"
WEAR = DATA / "wearables.csv"
INBODY = DATA / "inbody.csv"


def main():
    wear = pd.read_csv(WEAR)
    ib = pd.read_csv(INBODY)[["date", "weight_lbs", "body_fat_pct"]]

    # Drop existing weight columns if previous bridge ran (idempotent)
    for col in ("weight_lbs", "body_fat_pct"):
        if col in wear.columns:
            wear = wear.drop(columns=[col])

    merged = wear.merge(ib, on="date", how="left")

    # Reorder: drop 'source' last
    cols = [c for c in merged.columns if c != "source"] + ["source"]
    merged = merged[cols]

    merged.to_csv(WEAR, index=False)
    n_with_weight = merged["weight_lbs"].notna().sum()
    print(f"Wrote {len(merged)} rows with {n_with_weight} weight points ({n_with_weight} InBody scans matched)")


if __name__ == "__main__":
    main()
