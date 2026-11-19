"""Validate the rebuilt clinical-program eligibility layer."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"

PANEL = OUTPUT / "clinical_panel_2017_2026_eligibility_enriched.csv"
FIELDS = OUTPUT / "clinical_eligibility_fields.csv"
MATCHES = OUTPUT / "clinical_institution_degree_registry.csv"
VOCATIONAL = OUTPUT / "clinical_vocational_clinical_registry.csv"
SENSITIVITY = OUTPUT / "analysis_program_eligibility_sensitivity.csv"
SUMMARY = OUTPUT / "clinical_program_eligibility_summary.json"
NATIONAL_PROVINCES = OUTPUT / "analysis_national_primary_province_changes.csv"
NATIONAL_SUMMARY = OUTPUT / "analysis_national_primary_summary.json"
VALIDATION = OUTPUT / "clinical_eligibility_validation.json"
SOURCE_MANIFEST = ROOT / "data" / "moe" / "moe_source_manifest.csv"

PROGRAM_LEVELS = {
    "undergraduate",
    "vocational_three_year",
    "ambiguous_dual_offer",
    "unresolved",
}
PLAN_TYPES = {
    "ordinary_regular",
    "sino_foreign",
    "directed_employment",
    "public_funded_medical",
    "local_special",
    "national_special",
    "ethnic_class",
    "preparatory",
    "university_special",
    "other_special",
}
COUNT_DEFINITIONS = {
    "not_reported",
    "reported_count_definition_not_verified",
    "planned_places",
    "filed_candidates",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    panel = pd.read_csv(PANEL, low_memory=False)
    fields = pd.read_csv(FIELDS, low_memory=False)
    matches = pd.read_csv(MATCHES, low_memory=False)
    vocational = pd.read_csv(VOCATIONAL, low_memory=False)
    sensitivity = pd.read_csv(SENSITIVITY)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    national_provinces = pd.read_csv(NATIONAL_PROVINCES)
    national_summary = json.loads(
        NATIONAL_SUMMARY.read_text(encoding="utf-8")
    )
    with SOURCE_MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        source_manifest = list(csv.DictReader(handle))

    assert len(panel) == 36_866
    assert len(fields) == len(panel)
    assert len(matches) == 2_819
    assert len(source_manifest) == 329
    assert len(
        {
            row["file_path"]
            for row in source_manifest
        }
    ) == len(source_manifest)
    for row in source_manifest:
        path = ROOT / row["file_path"]
        assert path.exists(), path
        assert path.stat().st_size == int(row["bytes"]), path
        assert sha256(path) == row["sha256"], path
    assert not matches.duplicated(["university", "admission_year"]).any()
    assert not vocational.duplicated(
        ["registry_year", "school_code", "major_code", "registered_school_name"]
    ).any()

    assert set(panel["program_degree_level"]) <= PROGRAM_LEVELS
    assert set(panel["admission_plan_type"]) <= PLAN_TYPES
    assert set(panel["count_definition"]) <= COUNT_DEFINITIONS
    assert not panel[
        [
            "program_degree_level",
            "program_level_reason",
            "admission_plan_type",
            "count_definition",
        ]
    ].isna().any().any()

    expected_program_counts = {
        "undergraduate": 35_395,
        "vocational_three_year": 666,
        "ambiguous_dual_offer": 298,
        "unresolved": 507,
    }
    assert panel["program_degree_level"].value_counts().to_dict() == (
        expected_program_counts
    )

    primary = panel["primary_eligible_candidate"].astype(bool)
    assert primary.equals(
        panel["program_degree_level"].eq("undergraduate")
        & panel["admission_plan_type"].eq("ordinary_regular")
        & ~panel["sino_foreign"].astype(bool)
    )
    assert (
        panel.loc[primary, "institution_degree_level"].eq("本科").all()
    )
    assert (
        panel.loc[primary, "program_degree_level"].eq("undergraduate").all()
    )
    assert (
        panel.loc[primary, "admission_plan_type"].eq("ordinary_regular").all()
    )
    assert int(panel["primary_eligible_candidate"].sum()) == 34_484

    shandong_modern = panel[
        panel["year"].eq(2024)
        & panel["province"].eq("山东")
        & panel["university"].eq("山东现代学院")
    ]
    assert len(shandong_modern) == 1
    assert (
        shandong_modern["program_degree_level"].iloc[0]
        == "vocational_three_year"
    )
    assert (
        shandong_modern["program_level_reason"].iloc[0]
        == "manual_admission_plan_override"
    )

    expected_scenarios = {
        "current_all_clinical",
        "exclude_special_entry",
        "undergraduate_program_only",
        "ordinary_undergraduate_primary",
        "ordinary_undergraduate_primary_exact_deduplicated",
        "ordinary_undergraduate_primary_business_key_deduplicated",
        "ordinary_undergraduate_ambiguous_upper_bound",
        "ordinary_undergraduate_with_sino_foreign",
    }
    assert set(sensitivity["scenario"]) == expected_scenarios
    assert (
        sensitivity["recent_eligible_provinces_all_clinical"].eq(30).all()
    )
    assert (sensitivity["mean_all_change_all_clinical"] < 0).all()
    assert (sensitivity["mean_balanced_change_all_clinical"] < 0).all()
    assert (
        sensitivity["candidate_eligible_provinces_all_clinical"].eq(30).all()
    )
    assert (sensitivity["candidate_mean_all_change_all_clinical"] < 0).all()
    assert (
        sensitivity["candidate_mean_balanced_change_all_clinical"] < 0
    ).all()

    primary_row = sensitivity[
        sensitivity["scenario"].eq("ordinary_undergraduate_primary")
    ].iloc[0]
    upper_row = sensitivity[
        sensitivity["scenario"].eq(
            "ordinary_undergraduate_ambiguous_upper_bound"
        )
    ].iloc[0]
    assert (
        upper_row["records_included"] > primary_row["records_included"]
    )
    exact_row = sensitivity[
        sensitivity["scenario"].eq(
            "ordinary_undergraduate_primary_exact_deduplicated"
        )
    ].iloc[0]
    business_row = sensitivity[
        sensitivity["scenario"].eq(
            "ordinary_undergraduate_primary_business_key_deduplicated"
        )
    ].iloc[0]
    assert exact_row["records_included"] == 33_650
    assert business_row["records_included"] == 33_448
    assert (
        exact_row["mean_all_change_all_clinical"] < 0
        and exact_row["mean_balanced_change_all_clinical"] < 0
    )
    assert (
        business_row["mean_all_change_all_clinical"] < 0
        and business_row["mean_balanced_change_all_clinical"] < 0
    )
    assert abs(primary_row["mean_all_change_all_clinical"] - (-10.343571)) < 1e-3
    assert abs(
        primary_row["mean_balanced_change_all_clinical"] - (-0.843894)
    ) < 1e-3
    assert (
        abs(primary_row["candidate_mean_all_change_all_clinical"] - (-9.550840))
        < 1e-3
    )
    assert (
        abs(
            primary_row["candidate_mean_balanced_change_all_clinical"]
            - (-3.902529)
        )
        < 1e-3
    )

    assert len(national_provinces) == 30
    assert national_provinces["province"].is_unique
    assert national_summary["panel_records"] == len(panel)
    assert national_summary["primary_records"] == 34_484
    assert national_summary["paired_provinces"] == 30
    national_expected = {
        "programme_pool_available_schools": (-10.343571, 29),
        "programme_pool_fixed_schools": (-0.843894, 18),
        "candidate_distribution_available_schools": (-9.550840, 29),
        "candidate_distribution_fixed_schools": (-3.902529, 28),
    }
    for name, (expected_mean, expected_declining) in national_expected.items():
        metric = national_summary["summary"][name]
        assert abs(metric["mean_pp"] - expected_mean) < 1e-3
        assert metric["declining_provinces"] == expected_declining
    assert {
        name: national_summary["source_transitions"][name]["provinces"]
        for name in ("A_to_A", "B_to_A", "B_to_B")
    } == {"A_to_A": 1, "B_to_A": 5, "B_to_B": 24}

    assert summary["panel_rows"] == len(panel)
    assert summary["manual_program_level_overrides_applied"] == 1
    assert summary["program_degree_level_counts"] == expected_program_counts

    result = {
        "status": "passed",
        "panel_rows": len(panel),
        "institution_year_pairs": len(matches),
        "vocational_registry_rows": len(vocational),
        "program_degree_level_counts": expected_program_counts,
        "admission_plan_type_counts": (
            panel["admission_plan_type"].value_counts().to_dict()
        ),
        "primary_eligible_candidate_rows": int(primary.sum()),
        "manual_overrides_applied": 1,
        "source_cache_files_verified": len(source_manifest),
        "sensitivity_scenarios": len(sensitivity),
        "direction_negative_in_all_scenarios": True,
        "national_primary_paired_provinces": len(national_provinces),
        "national_primary_candidate_declining_provinces": (
            national_summary["summary"][
                "candidate_distribution_fixed_schools"
            ]["declining_provinces"]
        ),
    }
    VALIDATION.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
