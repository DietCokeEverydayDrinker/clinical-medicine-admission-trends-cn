"""Build row-level reconciliation for official endpoint panel differences."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = (
    ROOT
    / "output"
    / "official_endpoints"
    / "clinical_official_endpoints_2025_2026.csv"
)
PANEL = (
    ROOT
    / "output"
    / "clinical_panel_2017_2026_eligibility_enriched.csv"
)
OUTPUT = ROOT / "output" / "official_endpoints"
ROWS_OUTPUT = OUTPUT / "official_endpoint_panel_reconciliation.csv"
SUMMARY_OUTPUT = OUTPUT / "official_endpoint_panel_reconciliation_summary.json"

NAME_ALIASES = {
    "复旦大学医学院": "复旦大学上海医学院",
    "陆军军医大学": "中国人民解放军陆军军医大学",
    "遵义医科大学医学与科技学": "遵义医科大学医学与科技学院",
}


def normalize_name(value: object) -> str:
    name = str(value or "").replace("\u3000", "").replace(" ", "").strip()
    name = re.sub(r"\([^()]*\)$", "", name)
    return NAME_ALIASES.get(name, name)


def infer_plan_type(value: object) -> str:
    text = str(value or "")
    if "国家专项" in text:
        return "national_special"
    if "地方专项" in text:
        return "local_special"
    if "中外合作" in text:
        return "sino_foreign"
    if "定向" in text:
        return "directed_employment"
    if "公费" in text or "免费医学" in text:
        return "public_funded_medical"
    if "民族" in text:
        return "ethnic_class"
    if "预科" in text:
        return "preparatory"
    return "ordinary_regular"


def load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    official = pd.read_csv(
        OFFICIAL,
        dtype={"university_code": str, "major_code": str},
    )
    panel = pd.read_csv(
        PANEL,
        dtype={"university_code": str, "major_code": str},
        low_memory=False,
    )
    for frame in (official, panel):
        frame["_score"] = pd.to_numeric(frame["min_score"], errors="coerce")
        frame["_rank"] = pd.to_numeric(frame["min_rank"], errors="coerce")
    official["_plan_type"] = official["major"].map(infer_plan_type)
    official["_base_name"] = official["university"].map(normalize_name)
    panel["_plan_type"] = panel["admission_plan_type"]
    panel["_base_name"] = panel["university"].map(normalize_name)
    return official, panel


def source_frames(
    official: pd.DataFrame,
    panel: pd.DataFrame,
    province: str,
    year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    official_source = official[
        official["province"].eq(province) & official["year"].eq(year)
    ].copy()
    panel_source = panel[
        panel["province"].eq(province) & panel["year"].eq(year)
    ].copy()

    if year == 2026:
        for frame in (official_source, panel_source):
            frame["_code"] = (
                frame["university_code"].fillna("").astype(str).str.strip()
            )
        return (
            official_source,
            panel_source,
            ["_code", "_score", "_rank", "_plan_type"],
        )

    # The 2025 Chongqing panel predates alphanumeric offer-code retention.
    # Match on the normalized parent-institution name and score instead.
    return official_source, panel_source, ["_base_name", "_score", "_plan_type"]


def reconciliation_note(province: str, year: int, status: str) -> str:
    if status == "panel_only":
        return (
            "Same standard score, rank and Sino-foreign offer is represented "
            "under both the parent university and the joint institute name."
        )
    if province == "贵州":
        return (
            "Official ordinary-batch row absent from the current panel; "
            "admit_count is the filed-candidate count."
        )
    return (
        "Official ordinary-batch row absent from the current panel; "
        "count fields are not reported in this source."
    )


def coalesce(frame: pd.DataFrame, *columns: str) -> pd.Series:
    available = [column for column in columns if column in frame.columns]
    if not available:
        return pd.Series(index=frame.index, dtype=float)
    result = frame[available[0]]
    for column in available[1:]:
        result = result.combine_first(frame[column])
    return result


def build_reconciliation() -> tuple[pd.DataFrame, dict[str, object]]:
    official, panel = load_frames()
    all_rows: list[pd.DataFrame] = []
    summaries: list[dict[str, object]] = []

    for province, year in [("重庆", 2025), ("重庆", 2026), ("贵州", 2026)]:
        official_source, panel_source, keys = source_frames(
            official,
            panel,
            province,
            year,
        )
        for frame in (official_source, panel_source):
            frame["_occurrence"] = frame.groupby(
                keys,
                dropna=False,
            ).cumcount()
        merge_keys = [*keys, "_occurrence"]
        merged = official_source.merge(
            panel_source,
            on=merge_keys,
            how="outer",
            indicator=True,
            suffixes=("_official", "_panel"),
        )
        matched = int(merged["_merge"].eq("both").sum())
        official_only = merged["_merge"].eq("left_only")
        panel_only = merged["_merge"].eq("right_only")

        common = pd.DataFrame(
            {
                "province": province,
                "year": year,
                "reconciliation_status": merged["_merge"].map(
                    {
                        "left_only": "official_only",
                        "right_only": "panel_only",
                    }
                ),
                "university": merged["university_official"].where(
                    official_only,
                    merged["university_panel"],
                ),
                "university_code": merged["university_code_official"].where(
                    official_only,
                    merged["university_code_panel"],
                ),
                "major": merged["major_official"].where(
                    official_only,
                    merged["major_panel"],
                ),
                "major_code": merged["major_code_official"].where(
                    official_only,
                    merged["major_code_panel"],
                ),
                "min_score": merged["_score"],
                "min_rank": coalesce(
                    merged,
                    "_rank",
                    "_rank_official",
                    "_rank_panel",
                ),
                "admission_plan_type": merged["_plan_type"],
                "program_degree_level": merged[
                    "program_degree_level"
                ].where(panel_only, "undergraduate"),
                "primary_eligible_candidate": merged[
                    "primary_eligible_candidate"
                ],
                "count_definition": merged["count_definition"],
                "source_row": merged["source_row"],
                "source_sequence": merged["source_sequence"],
                "panel_source_file": merged["source_file_panel"],
            }
        )
        differences = common[
            common["reconciliation_status"].isin(["official_only", "panel_only"])
        ].copy()
        differences["note"] = differences.apply(
            lambda row: reconciliation_note(
                province,
                year,
                str(row["reconciliation_status"]),
            ),
            axis=1,
        )
        all_rows.append(differences)

        summaries.append(
            {
                "province": province,
                "year": year,
                "official_rows": int(len(official_source)),
                "panel_rows": int(len(panel_source)),
                "matched_rows": matched,
                "official_only_rows": int(official_only.sum()),
                "panel_only_rows": int(panel_only.sum()),
                "official_only_plan_types": (
                    merged.loc[official_only, "_plan_type"]
                    .value_counts()
                    .sort_index()
                    .to_dict()
                ),
                "batch": sorted(
                    str(value)
                    for value in official_source["batch"].dropna().unique()
                ),
            }
        )

    output = pd.concat(all_rows, ignore_index=True)
    output = output.sort_values(
        ["province", "year", "reconciliation_status", "university", "min_score"]
    )
    summary = {
        "sources": summaries,
        "total_official_only_rows": int(
            output["reconciliation_status"].eq("official_only").sum()
        ),
        "total_panel_only_rows": int(
            output["reconciliation_status"].eq("panel_only").sum()
        ),
        "status": "passed",
    }
    for source in summaries:
        assert (
            source["matched_rows"] + source["official_only_rows"]
            == source["official_rows"]
        )
        assert (
            source["matched_rows"] + source["panel_only_rows"]
            == source["panel_rows"]
        )
    assert summary["total_official_only_rows"] == 14
    assert summary["total_panel_only_rows"] == 1
    return output, summary


def main() -> None:
    rows, summary = build_reconciliation()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows.to_csv(ROWS_OUTPUT, index=False, encoding="utf-8-sig")
    SUMMARY_OUTPUT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
