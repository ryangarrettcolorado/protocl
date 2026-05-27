"""
One-shot: consolidate same-day cycling activities that were double-counted
because Apple HK labels them 'Cycling' (ride) while Strava labels them
'MountainBikeRide' (mtb). They share identical distance_miles (HK source =
Strava source for outdoor rides), so distance equality + same date is a
strong dedup key.

Merge rule:
  Among rows where activity_type ∈ {ride, mtb, ebike} sharing same date and
  distance_miles match within ±0.05 miles:
    - keep the row with the richer field-set (more non-null among HR/power/cadence/tss/elevation)
    - merge missing fields from the other row(s) into the keeper
    - drop the loser(s)
"""
from __future__ import annotations

import pandas as pd
from pathlib import Path

TRAINING = Path(__file__).resolve().parent.parent / "data" / "ryan" / "training.csv"

CYCLING_TYPES = {"ride", "mtb", "ebike"}
RICH_FIELDS = [
    "avg_hr_bpm", "max_hr_bpm", "avg_power_watts",
    "avg_cadence_rpm", "tss", "elevation_ft", "calories",
]


def richness(row: pd.Series) -> int:
    return sum(1 for f in RICH_FIELDS if pd.notna(row.get(f)))


def merge_into(keeper: pd.Series, loser: pd.Series) -> pd.Series:
    """Pull missing fields from loser into keeper. Return updated keeper."""
    out = keeper.copy()
    for f in RICH_FIELDS + ["duration_min"]:
        if pd.isna(out.get(f)) and pd.notna(loser.get(f)):
            out[f] = loser[f]
    # Combine notes & sources for provenance
    keeper_notes = "" if pd.isna(out.get("notes")) else str(out["notes"])
    loser_notes = "" if pd.isna(loser.get("notes")) else str(loser["notes"])
    # Pull strava_id from loser if not already in keeper notes
    if "strava_id:" in loser_notes and "strava_id:" not in keeper_notes:
        sid_part = next((p for p in loser_notes.split("·") if "strava_id:" in p), "")
        if sid_part:
            sep = " · " if keeper_notes else ""
            out["notes"] = f"{keeper_notes}{sep}{sid_part.strip()}"
    # Merge sources
    keeper_src = str(out.get("source", ""))
    loser_src = str(loser.get("source", ""))
    if loser_src and loser_src not in keeper_src:
        out["source"] = f"{keeper_src}+{loser_src.replace('+','')}".replace("apple_healthkit+apple_healthkit", "apple_healthkit")
    return out


def main():
    df = pd.read_csv(TRAINING)
    print(f"Loaded {len(df)} rows")

    cycling_mask = df["activity_type"].isin(CYCLING_TYPES)
    cycling = df[cycling_mask].copy()
    print(f"Cycling rows: {len(cycling)}")

    to_drop = set()
    to_update: dict[int, pd.Series] = {}

    # Group cycling rows by date, look for distance matches
    for date, group in cycling.groupby("date"):
        if len(group) < 2:
            continue
        # For each pair (i<j), check distance match
        idxs = group.index.tolist()
        for i_pos, i in enumerate(idxs):
            if i in to_drop:
                continue
            for j in idxs[i_pos + 1:]:
                if j in to_drop:
                    continue
                row_i = df.loc[i]
                row_j = df.loc[j]
                di = row_i["distance_miles"]
                dj = row_j["distance_miles"]
                if pd.isna(di) or pd.isna(dj):
                    continue
                if abs(di - dj) > 0.05:
                    continue
                # Match! Pick keeper by richness
                r_i = richness(row_i)
                r_j = richness(row_j)
                if r_i >= r_j:
                    keeper_idx, loser_idx = i, j
                else:
                    keeper_idx, loser_idx = j, i
                merged = merge_into(df.loc[keeper_idx], df.loc[loser_idx])
                to_update[keeper_idx] = merged
                to_drop.add(loser_idx)
                print(
                    f"  {date}: merge row {loser_idx} ({df.loc[loser_idx,'activity_type']}, "
                    f"{df.loc[loser_idx,'source']}) → row {keeper_idx} "
                    f"({df.loc[keeper_idx,'activity_type']}, {df.loc[keeper_idx,'source']}) "
                    f"@ {di} mi"
                )

    # Apply updates
    for idx, row in to_update.items():
        for col in df.columns:
            df.at[idx, col] = row[col]
    # Drop losers
    df = df.drop(index=list(to_drop)).reset_index(drop=True)
    df = df.sort_values("date").reset_index(drop=True)

    df.to_csv(TRAINING, index=False)
    print(f"\nMerged {len(to_drop)} duplicate cycling rows")
    print(f"Final row count: {len(df)}")

    # Re-report coverage
    cycling = df[df["activity_type"].isin(CYCLING_TYPES)]
    print(f"\nCycling coverage after dedup ({len(cycling)} rows):")
    for col in RICH_FIELDS:
        pct = cycling[col].notna().sum() / len(cycling) * 100
        print(f"  {col}: {cycling[col].notna().sum()}/{len(cycling)} ({pct:.0f}%)")


if __name__ == "__main__":
    main()
