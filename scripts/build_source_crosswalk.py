"""Build a row-level crosswalk from analysis sources to the source manifest."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PANEL = OUTPUT / "clinical_panel_2017_2026_candidate_percentile.csv"
MANIFEST = OUTPUT / "clinical_source_manifest.csv"
CROSSWALK = OUTPUT / "clinical_source_crosswalk.csv"


def combine(values: pd.Series) -> str:
    clean = sorted(
        {
            str(value).strip()
            for value in values
            if pd.notna(value) and str(value).strip()
        }
    )
    return "|".join(clean)


def main() -> None:
    panel = pd.read_csv(
        PANEL,
        usecols=[
            "source_file",
            "province",
            "year",
            "clinical_track",
            "admission_percentile",
            "candidate_percentile",
        ],
        low_memory=False,
    )
    manifest = pd.read_csv(MANIFEST, low_memory=False)

    panel["source_file"] = panel["source_file"].fillna("").astype(str).str.strip()
    panel["source_file"] = panel["source_file"].replace("", "<blank>")
    manifest["file_name"] = manifest["file_name"].fillna("").astype(str).str.strip()

    panel_summary = (
        panel.groupby("source_file", dropna=False)
        .agg(
            panel_rows=("source_file", "size"),
            panel_provinces=("province", combine),
            panel_years=("year", combine),
            panel_tracks=("clinical_track", combine),
            admission_percentile_rows=(
                "admission_percentile",
                lambda values: int(values.notna().sum()),
            ),
            candidate_percentile_rows=(
                "candidate_percentile",
                lambda values: int(values.notna().sum()),
            ),
        )
        .reset_index()
    )

    manifest_summary = (
        manifest[manifest["file_name"].ne("")]
        .groupby("file_name", dropna=False)
        .agg(
            manifest_match_count=("source_id", "nunique"),
            source_ids=("source_id", combine),
            usage_roles=("usage_role", combine),
            manifest_provinces=("province", combine),
            manifest_years=("year", combine),
            providers=("provider_organization", combine),
            page_urls=("page_url", combine),
            attachment_urls=("attachment_url", combine),
            manifest_tiers=("source_tier", combine),
            validation_statuses=("validation_status", combine),
        )
        .reset_index()
        .rename(columns={"file_name": "source_file"})
    )

    crosswalk = panel_summary.merge(
        manifest_summary, on="source_file", how="left"
    )
    crosswalk["match_status"] = crosswalk["manifest_match_count"].apply(
        lambda value: "matched" if pd.notna(value) and int(value) > 0 else "unmatched"
    )
    crosswalk = crosswalk.sort_values(
        ["match_status", "source_file"], ascending=[False, True]
    )
    crosswalk.to_csv(CROSSWALK, index=False, encoding="utf-8-sig")

    assert int(crosswalk["panel_rows"].sum()) == len(panel)
    unmatched = crosswalk[crosswalk["match_status"].eq("unmatched")]
    print(f"Wrote {len(crosswalk):,} source crosswalk rows")
    print(f"Matched source files: {len(crosswalk) - len(unmatched):,}")
    print(f"Unmatched source files: {len(unmatched):,}")
    if len(unmatched):
        print("\n".join(unmatched["source_file"].tolist()))


if __name__ == "__main__":
    main()
