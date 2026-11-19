"""Export national primary-candidate changes for the journal manuscript.

The national comparison is an ecological measurement analysis. Each school
contributes its within-year median across eligible clinical offers, each
province contributes its median across schools, and provinces are weighted
equally. The script writes province-level estimates so that every summary can
be checked without re-running the full eligibility build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
PANEL = OUTPUT / "clinical_panel_2017_2026_eligibility_enriched.csv"
SENSITIVITY = OUTPUT / "analysis_program_eligibility_sensitivity.csv"
PROVINCE_OUTPUT = OUTPUT / "analysis_national_primary_province_changes.csv"
SUMMARY_OUTPUT = OUTPUT / "analysis_national_primary_summary.json"
PACKAGED_SENSITIVITY = OUTPUT / "analysis_national_primary_sensitivity.csv"

sys.path.insert(0, str(ROOT / "scripts"))
import analyze_trends as analysis  # noqa: E402


def parse_bool(values: pd.Series) -> pd.Series:
    return values.astype(str).str.strip().str.lower().isin({"true", "1"})


def summarize_changes(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return {
        "provinces": int(len(clean)),
        "mean_pp": float(clean.mean()),
        "median_pp": float(clean.median()),
        "declining_provinces": int(clean.lt(0).sum()),
        "increasing_provinces": int(clean.gt(0).sum()),
        "unchanged_provinces": int(clean.eq(0).sum()),
    }


def main() -> None:
    panel = pd.read_csv(PANEL, low_memory=False)
    panel = panel[
        panel["subject"].eq("clinical")
        & panel["university"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    primary = panel[parse_bool(panel["primary_eligible_candidate"])].copy()

    school_layer, province_layer = analysis.build_analysis_layer(primary)
    programme = analysis.build_recent_balanced_change(
        school_layer,
        province_layer,
        metric="admission_percentile",
    )
    candidate = analysis.build_recent_balanced_change(
        school_layer,
        province_layer,
        metric="candidate_percentile",
    )

    programme = programme[
        programme["track"].eq("all_clinical")
        & programme["comparison_eligible"]
    ].copy()
    candidate = candidate[
        candidate["track"].eq("all_clinical")
        & candidate["comparison_eligible"]
    ].copy()

    programme_columns = {
        "all_2025": "programme_pool_all_2025",
        "all_2026": "programme_pool_all_2026",
        "all_change": "programme_pool_all_change_pp",
        "n_schools_all_2025": "programme_pool_n_schools_2025",
        "n_schools_all_2026": "programme_pool_n_schools_2026",
        "balanced_2025": "programme_pool_fixed_2025",
        "balanced_2026": "programme_pool_fixed_2026",
        "balanced_change": "programme_pool_fixed_change_pp",
        "n_schools_balanced": "programme_pool_n_schools_fixed",
        "source_group_2026": "source_group_2026",
    }
    candidate_columns = {
        "all_2025": "candidate_all_2025",
        "all_2026": "candidate_all_2026",
        "all_change": "candidate_all_change_pp",
        "n_schools_all_2025": "candidate_n_schools_2025",
        "n_schools_all_2026": "candidate_n_schools_2026",
        "balanced_2025": "candidate_fixed_2025",
        "balanced_2026": "candidate_fixed_2026",
        "balanced_change": "candidate_fixed_change_pp",
        "n_schools_balanced": "candidate_n_schools_fixed",
    }
    province_changes = programme[["province", *programme_columns]].rename(
        columns=programme_columns
    )
    province_changes = province_changes.merge(
        candidate[["province", *candidate_columns]].rename(
            columns=candidate_columns
        ),
        on="province",
        how="left",
        validate="one_to_one",
    )

    source = province_layer[
        province_layer["track"].eq("all_clinical")
        & province_layer["metric"].eq("admission_percentile")
        & province_layer["year"].isin([2025, 2026])
    ].pivot(index="province", columns="year", values="source_group")
    source = source.rename(
        columns={
            2025: "source_group_2025",
            2026: "source_group_2026_checked",
        }
    )
    province_changes = province_changes.merge(
        source,
        left_on="province",
        right_index=True,
        how="left",
        validate="one_to_one",
    )
    province_changes["source_transition"] = (
        province_changes["source_group_2025"].fillna("unknown")
        + "_to_"
        + province_changes["source_group_2026_checked"].fillna("unknown")
    )
    assert province_changes["source_group_2026"].eq(
        province_changes["source_group_2026_checked"]
    ).all()
    province_changes = province_changes.drop(
        columns=["source_group_2026_checked"]
    )
    province_changes = province_changes.sort_values(
        "candidate_all_change_pp",
        ascending=True,
        na_position="last",
    )
    province_changes.to_csv(
        PROVINCE_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    change_columns = {
        "programme_pool_all_change_pp": (
            "programme_pool_available_schools"
        ),
        "programme_pool_fixed_change_pp": (
            "programme_pool_fixed_schools"
        ),
        "candidate_all_change_pp": (
            "candidate_distribution_available_schools"
        ),
        "candidate_fixed_change_pp": (
            "candidate_distribution_fixed_schools"
        ),
    }
    summaries = {
        label: summarize_changes(province_changes[column])
        for column, label in change_columns.items()
    }
    source_transitions = {}
    for transition, group in province_changes.groupby(
        "source_transition", sort=True
    ):
        source_transitions[transition] = {
            "provinces": int(len(group)),
            **{
                label: summarize_changes(group[column])
                for column, label in change_columns.items()
            },
        }

    summary = {
        "panel_records": int(len(panel)),
        "primary_records": int(len(primary)),
        "excluded_records": int(len(panel) - len(primary)),
        "paired_provinces": int(len(province_changes)),
        "summary": summaries,
        "source_transitions": source_transitions,
        "direction": (
            "negative values mean a lower programme-pool percentile or a "
            "lower candidate-distribution percentile in 2026"
        ),
    }
    SUMMARY_OUTPUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    sensitivity = pd.read_csv(SENSITIVITY)
    sensitivity = sensitivity.rename(
        columns={
            "mean_all_change_all_clinical": "programme_pool_available_pp",
            "mean_balanced_change_all_clinical": (
                "programme_pool_fixed_pp"
            ),
            "candidate_mean_all_change_all_clinical": (
                "candidate_distribution_available_pp"
            ),
            "candidate_mean_balanced_change_all_clinical": (
                "candidate_distribution_fixed_pp"
            ),
        }
    )
    sensitivity.to_csv(
        PACKAGED_SENSITIVITY,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        f"Wrote {PROVINCE_OUTPUT.name} ({len(province_changes)} provinces), "
        f"{SUMMARY_OUTPUT.name}, and {PACKAGED_SENSITIVITY.name}"
    )


if __name__ == "__main__":
    main()
