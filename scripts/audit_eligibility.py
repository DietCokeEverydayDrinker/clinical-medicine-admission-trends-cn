"""Audit study-eligibility flags and their effect on recent estimates."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
INPUT = OUTPUT / "clinical_panel_2017_2026_candidate_percentile.csv"
RECORD_AUDIT = OUTPUT / "clinical_eligibility_audit.csv"
SENSITIVITY = OUTPUT / "analysis_eligibility_sensitivity.csv"

sys.path.insert(0, str(ROOT / "scripts"))
import analyze_trends as analysis  # noqa: E402


SPECIAL_ENTRY_PATTERN = re.compile(
    r"国家专项|地方专项|高校专项|专项计划|民族班|预科班|预科|"
    r"定向|公费医学|免费医学|农村卫生定向|振兴龙江计划|固边计划"
)
FOREIGN_COOPERATION_PATTERN = re.compile(
    r"中外合作办学|中外合作|合作办学"
)
VOCATIONAL_NAME_PATTERN = re.compile(
    r"(?:专科学校|职业技术学院|职业学院|高等专科学校)$"
)
VOCATIONAL_ALIASES = {
    "山东现代学院",
    "山东现代学院(民办)",
}


def eligibility_flags(frame: pd.DataFrame) -> pd.DataFrame:
    text = (
        frame["major"].fillna("").astype(str)
        + " "
        + frame["major_note"].fillna("").astype(str)
    )
    university = frame["university"].fillna("").astype(str).str.strip()

    special_entry = text.str.contains(SPECIAL_ENTRY_PATTERN, regex=True)
    foreign_cooperation = text.str.contains(
        FOREIGN_COOPERATION_PATTERN, regex=True
    )
    vocational = university.str.contains(
        VOCATIONAL_NAME_PATTERN, regex=True
    ) | university.isin(VOCATIONAL_ALIASES)

    return pd.DataFrame(
        {
            "special_entry_suspected": special_entry,
            "foreign_cooperation_suspected": foreign_cooperation,
            "vocational_name_rule_suspected": vocational,
            "core_ordinary_eligible": ~(special_entry | vocational),
            "strict_ordinary_eligible": ~(
                special_entry | vocational | foreign_cooperation
            ),
        },
        index=frame.index,
    )


def scenario_masks(flags: pd.DataFrame) -> dict[str, pd.Series]:
    all_rows = pd.Series(True, index=flags.index)
    return {
        "current_all_clinical": all_rows,
        "exclude_special_entry": ~flags["special_entry_suspected"],
        "exclude_vocational_name_rule": ~flags[
            "vocational_name_rule_suspected"
        ],
        "core_ordinary": flags["core_ordinary_eligible"],
        "strict_ordinary": flags["strict_ordinary_eligible"],
    }


def summarize_scenarios(
    frame: pd.DataFrame, masks: dict[str, pd.Series]
) -> pd.DataFrame:
    rows = []
    for scenario, keep in masks.items():
        selected = frame[keep].copy()
        school_layer, province_layer = analysis.build_analysis_layer(selected)
        recent = analysis.build_recent_balanced_change(
            school_layer, province_layer
        )
        all_clinical = recent[
            recent["track"].eq("all_clinical")
            & recent["comparison_eligible"]
        ]
        five_year = recent[
            recent["track"].eq("five_year")
            & recent["comparison_eligible"]
        ]
        eight_year = recent[
            recent["track"].eq("eight_year")
            & recent["comparison_eligible"]
        ]
        rows.append(
            {
                "scenario": scenario,
                "records_included": len(selected),
                "records_excluded": int((~keep).sum()),
                "recent_eligible_provinces_all_clinical": (
                    all_clinical["province"].nunique()
                ),
                "recent_eligible_provinces_five_year": (
                    five_year["province"].nunique()
                ),
                "recent_eligible_provinces_eight_year": (
                    eight_year["province"].nunique()
                ),
                "mean_all_change_all_clinical": all_clinical[
                    "all_change"
                ].mean(),
                "median_all_change_all_clinical": all_clinical[
                    "all_change"
                ].median(),
                "mean_balanced_change_all_clinical": all_clinical[
                    "balanced_change"
                ].mean(),
                "median_balanced_change_all_clinical": all_clinical[
                    "balanced_change"
                ].median(),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    frame = pd.read_csv(INPUT, low_memory=False)
    frame = frame[
        frame["subject"].eq("clinical")
        & frame["university"].fillna("").astype(str).ne("")
    ].copy()
    frame["university"] = frame["university"].fillna("").astype(str).str.strip()

    flags = eligibility_flags(frame)
    audit_columns = [
        "province",
        "province_slug",
        "year",
        "subject",
        "clinical_track",
        "batch",
        "university",
        "major",
        "major_note",
        "admission_percentile",
        "source_tier",
        "source_file",
    ]
    audit = pd.concat(
        [frame[audit_columns].reset_index(drop=True), flags.reset_index(drop=True)],
        axis=1,
    )
    audit.to_csv(RECORD_AUDIT, index=False, encoding="utf-8-sig")

    summary = summarize_scenarios(frame, scenario_masks(flags))
    summary.to_csv(SENSITIVITY, index=False, encoding="utf-8-sig")

    print(f"Wrote {len(audit):,} eligibility-audit rows")
    print(f"Wrote {len(summary):,} sensitivity scenarios")
    print(
        summary[
            [
                "scenario",
                "records_excluded",
                "mean_all_change_all_clinical",
                "mean_balanced_change_all_clinical",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
