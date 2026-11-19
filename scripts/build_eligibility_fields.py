"""Build institution- and programme-level eligibility fields.

The university directory is sourced from the Ministry of Education annual
ordinary higher-education institution lists. Degree level is tracked by the
official school identifier so renamed institutions can be followed across
years.

The vocational programme register is sourced from the Ministry of Education
national vocational college major-register service. It identifies schools
approved to offer a three-year clinical medicine programme in each admission
year.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
SOURCE_CACHE = ROOT / "data" / "moe"
LEGACY_RAW = OUTPUT / "raw" / "moe"
RAW = SOURCE_CACHE if SOURCE_CACHE.exists() else LEGACY_RAW
PANEL = OUTPUT / "clinical_panel_2017_2026_candidate_percentile.csv"
DIRECTORY_YEARS = (2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026)
VOCATIONAL_YEARS = tuple(range(2017, 2027))
MANUAL_OVERRIDES = ROOT / "data" / "manual_program_level_overrides.csv"

INSTITUTION_REGISTRY = OUTPUT / "clinical_institution_degree_registry.csv"
VOCATIONAL_REGISTRY = OUTPUT / "clinical_vocational_clinical_registry.csv"
ELIGIBILITY_FIELDS = OUTPUT / "clinical_eligibility_fields.csv"
ENRICHED_PANEL = OUTPUT / "clinical_panel_2017_2026_eligibility_enriched.csv"
SENSITIVITY = OUTPUT / "analysis_program_eligibility_sensitivity.csv"
SUMMARY = OUTPUT / "clinical_program_eligibility_summary.json"

sys.path.insert(0, str(ROOT / "scripts"))
import analyze_trends as analysis  # noqa: E402


ALIASES = {
    "上海交通大学医学院": "上海交通大学",
    "北京大学医学部": "北京大学",
    "复旦大学上海医学院": "复旦大学",
    "复旦大学医学院": "复旦大学",
    "浙江大学医学院": "浙江大学",
    "东南大学医学院": "东南大学",
    "汕头大学医学院": "汕头大学",
    "南昌大学抚州医学院": "南昌大学",
    "山西医科大学汾阳学院": "山西医科大学",
    "内蒙古科技大学包头医学院": "内蒙古科技大学",
    "上海交通大学医学院(本博连读)": "上海交通大学",
    "上海交通大学医学院(本博莲读)": "上海交通大学",
}

MILITARY_INSTITUTIONS = {
    "中国人民解放军陆军工程大学": ("中国人民解放军陆军工程大学", "本科"),
    "陆军军医大学": ("陆军军医大学", "本科"),
    "空军军医大学": ("空军军医大学", "本科"),
    "海军军医大学": ("海军军医大学", "本科"),
    "中国人民解放军陆军军医大学": ("陆军军医大学", "本科"),
    "中国人民解放军空军军医大学": ("空军军医大学", "本科"),
    "中国人民解放军海军军医大学": ("海军军医大学", "本科"),
}

SPECIAL_PATTERNS = {
    "public_funded_medical": (
        r"公费医学|免费医学|公费医学生|免费医学生|农村卫生定向"
    ),
    "national_special": r"国家专项",
    "local_special": r"地方专项|地方农村专项",
    "university_special": r"高校专项",
    "ethnic_class": (
        r"民族班|少数民族班|民族预科|"
        r"只招(?:收)?[^，。；;]{0,24}少数民族|"
        r"招收[^，。；;]{0,20}少数民族考生"
    ),
    "preparatory": r"预科班|预科",
    "directed_employment": r"定向",
    "other_special": (
        r"专项计划|振兴龙江计划|固边计划|南疆单列|援疆|内地新疆|内地西藏"
    ),
}

SINO_FOREIGN_PATTERN = r"中外合作办学|中外合作|合作办学"
EXPLICIT_VOCATIONAL_BATCH = re.compile(r"专科|高职|普通类二段")
EXPLICIT_UNDERGRADUATE_BATCH = re.compile(
    r"本科|本一|本二|一本|二本|本科批|本科一批|本科二批|本科三批"
)
DEDUP_KEY = [
    "province",
    "year",
    "category",
    "batch",
    "university",
    "major",
    "major_note",
    "university_code",
    "major_code",
    "major_group",
]


def normalize_institution_name(value: object) -> str:
    """Normalize presentation noise while preserving institution identity."""

    text = str(value).strip()
    text = (
        text.replace("（", "(")
        .replace("）", ")")
        .replace("［", "[")
        .replace("］", "]")
        .replace("\u3000", "")
        .replace(" ", "")
    )
    text = re.sub(r"\[[^]]*\]", "", text)
    annotation = re.compile(
        r"\((?:[^()]*(?:市|省|区|县|旗|盟|州|公办|民办|独立学院|"
        r"一流大学建设高校|一流学科建设高校|本博连读|本博莲读|"
        r"中外合作办学|地方专项计划|国家专项计划|高校专项计划|"
        r"其他单列|临床)[^()]*)\)"
    )
    previous = None
    while previous != text:
        previous = text
        text = annotation.sub("", text)
    text = re.sub(r"\d+$", "", text)
    return text.strip()


def load_institution_registry() -> pd.DataFrame:
    frames = []
    for year in DIRECTORY_YEARS:
        path = RAW / f"moe_universities_{year}.xls"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {path}. Run the directory download step first."
            )
        frame = pd.read_excel(path, header=None)
        frame = frame[frame[5].isin(["本科", "专科"])][[1, 2, 4, 5]].copy()
        frame.columns = [
            "registry_name",
            "school_code",
            "registry_location",
            "institution_degree_level",
        ]
        frame["registry_year"] = year
        frame["registry_name"] = frame["registry_name"].astype(str).str.strip()
        frame["school_code"] = frame["school_code"].astype(str).str.strip()
        frame["normalized_name"] = frame["registry_name"].map(
            normalize_institution_name
        )
        frames.append(frame)
    registry = pd.concat(frames, ignore_index=True)
    duplicates = registry.duplicated(["registry_year", "normalized_name"])
    if duplicates.any():
        raise ValueError(
            "Institution registry contains duplicate normalized names within a year."
        )
    return registry


def load_vocational_registry() -> pd.DataFrame:
    rows = []
    for year in VOCATIONAL_YEARS:
        paths = sorted((RAW / "vocational_clinical").glob(f"{year}_*.json"))
        if not paths:
            raise FileNotFoundError(
                f"No vocational clinical registrations cached for {year}."
            )
        for path in paths:
            payload = json.loads(path.read_text(encoding="utf-8"))
            data = payload.get("data") or {}
            for item in data.get("list") or []:
                row = dict(item)
                row["registry_year"] = year
                rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.rename(
        columns={
            "prov_name": "registry_province",
            "major_code": "major_code",
            "major_name": "registered_major_name",
            "school_code": "school_code",
            "school_name": "registered_school_name",
            "school_system": "program_duration_years",
            "remark": "registration_remark",
        }
    )
    frame["school_code"] = frame["school_code"].astype(str).str.strip()
    frame["registered_school_name"] = (
        frame["registered_school_name"].astype(str).str.strip()
    )
    frame["registry_year"] = frame["registry_year"].astype(int)
    frame = frame.drop_duplicates(
        [
            "registry_year",
            "school_code",
            "major_code",
            "registered_school_name",
        ]
    )
    frame = frame.sort_values(
        ["registry_year", "registry_province", "registered_school_name"]
    )
    return frame.reset_index(drop=True)


def available_directory_year(admission_year: int) -> int:
    prior = [year for year in DIRECTORY_YEARS if year <= admission_year]
    if prior:
        return max(prior)
    return min(DIRECTORY_YEARS)


def build_institution_matches(
    panel: pd.DataFrame, registry: pd.DataFrame
) -> pd.DataFrame:
    name_codes: dict[str, list[str]] = {
        name: sorted(group["school_code"].unique())
        for name, group in registry.groupby("normalized_name")
    }
    code_years: dict[str, set[int]] = {
        code: set(group["registry_year"])
        for code, group in registry.groupby("school_code")
    }
    code_year_record = (
        registry.drop_duplicates(["school_code", "registry_year"])
        .set_index(["school_code", "registry_year"])
        .to_dict("index")
    )
    all_names = sorted(name_codes, key=len, reverse=True)

    unique_pairs = panel[["university", "year"]].drop_duplicates().copy()
    unique_pairs["university"] = (
        unique_pairs["university"].fillna("").astype(str).str.strip()
    )
    unique_pairs["registry_target_year"] = unique_pairs["year"].map(
        available_directory_year
    )
    unique_pairs["normalized_name"] = unique_pairs["university"].map(
        normalize_institution_name
    )

    matches = []
    for row in unique_pairs.itertuples(index=False):
        university = row.university
        target_year = int(row.registry_target_year)
        normalized = row.normalized_name
        matched_norm = normalized
        match_status = "unresolved"
        codes = name_codes.get(normalized, [])

        if normalized in ALIASES:
            matched_norm = normalize_institution_name(ALIASES[normalized])
            codes = name_codes.get(matched_norm, [])
            if codes:
                match_status = "alias"
        elif codes:
            match_status = "name_match"

        if not codes:
            prefixes = [
                name
                for name in all_names
                if len(name) >= 4
                and normalized.startswith(name)
                and normalized != name
            ]
            if prefixes:
                matched_norm = max(prefixes, key=len)
                codes = name_codes.get(matched_norm, [])
                if codes:
                    match_status = "parent_campus_prefix"

        match = None
        if codes:
            ranked_codes = []
            for code in codes:
                years = code_years[code]
                distance = min(abs(year - target_year) for year in years)
                ranked_codes.append((distance, -len(years), code))
            _, _, school_code = min(ranked_codes)
            prior_years = [
                year for year in code_years[school_code] if year <= target_year
            ]
            if prior_years:
                source_year = max(prior_years)
                match_status += "_prior_year"
            else:
                source_year = min(
                    code_years[school_code],
                    key=lambda year: abs(year - target_year),
                )
                match_status += "_future_year"
            match = code_year_record[(school_code, source_year)]
            match["school_code"] = school_code
            match["registry_year"] = source_year
        elif normalized in MILITARY_INSTITUTIONS:
            matched_name, degree_level = MILITARY_INSTITUTIONS[normalized]
            match = {
                "registry_name": matched_name,
                "school_code": "",
                "institution_degree_level": degree_level,
                "registry_year": target_year,
            }
            match_status = "military_manual"

        matches.append(
            {
                "university": university,
                "admission_year": int(row.year),
                "registry_target_year": target_year,
                "normalized_name": normalized,
                "matched_name": (
                    match["registry_name"] if match is not None else ""
                ),
                "school_code": (
                    str(match["school_code"]) if match is not None else ""
                ),
                "institution_degree_level": (
                    match["institution_degree_level"]
                    if match is not None
                    else "unresolved"
                ),
                "degree_level_source_year": (
                    int(match["registry_year"]) if match is not None else None
                ),
                "match_status": match_status,
            }
        )
    return pd.DataFrame(matches)


def classify_plan_type(frame: pd.DataFrame) -> pd.DataFrame:
    text = (
        frame["major"].fillna("").astype(str)
        + " "
        + frame["major_note"].fillna("").astype(str)
    )
    flags = pd.DataFrame(index=frame.index)
    for name, pattern in SPECIAL_PATTERNS.items():
        flags[name] = text.str.contains(pattern, regex=True, na=False)
    flags["sino_foreign"] = text.str.contains(
        SINO_FOREIGN_PATTERN, regex=True, na=False
    )
    flags["special_entry"] = flags[list(SPECIAL_PATTERNS)].any(axis=1)

    priority = [
        ("public_funded_medical", "public_funded_medical"),
        ("national_special", "national_special"),
        ("local_special", "local_special"),
        ("university_special", "university_special"),
        ("ethnic_class", "ethnic_class"),
        ("preparatory", "preparatory"),
        ("directed_employment", "directed_employment"),
        ("sino_foreign", "sino_foreign"),
        ("other_special", "other_special"),
    ]
    plan_type = pd.Series("ordinary_regular", index=frame.index)
    for flag, label in reversed(priority):
        plan_type.loc[flags[flag]] = label
    flags["admission_plan_type"] = plan_type
    return flags


def classify_program_level(frame: pd.DataFrame) -> pd.DataFrame:
    batch = frame["batch"].fillna("").astype(str)
    province = frame["province"].fillna("").astype(str)
    institution_level = frame["institution_degree_level"].fillna("unresolved")

    undergraduate_batch = batch.str.contains(EXPLICIT_UNDERGRADUATE_BATCH)
    shandong_first = province.eq("山东") & batch.eq("普通类一段")
    undergraduate_batch |= shandong_first

    registered = frame["vocational_clinical_registered"].fillna(False)
    province_school_year_has_undergraduate = (
        undergraduate_batch.groupby(
            [frame["province"], frame["university"], frame["year"]]
        ).transform("any")
    )
    level = pd.Series("unresolved", index=frame.index)
    reason = pd.Series("", index=frame.index)

    vocational_institution = institution_level.eq("专科")
    vocational_batch = (
        ~undergraduate_batch
        & batch.str.contains(EXPLICIT_VOCATIONAL_BATCH)
        & province_school_year_has_undergraduate
    )
    vocational = vocational_institution | vocational_batch
    level.loc[vocational] = "vocational_three_year"
    reason.loc[vocational_institution] = "institution_registry_vocational"
    reason.loc[vocational_batch & ~vocational_institution] = (
        "vocational_batch_with_vocational_clinical_registration"
    )

    clean_undergraduate = (
        (
            undergraduate_batch
            | (
                ~undergraduate_batch
                & (institution_level.eq("本科") | institution_level.eq("unresolved"))
                & ~registered
            )
        )
        & institution_level.eq("本科")
    )
    level.loc[clean_undergraduate] = "undergraduate"
    reason.loc[clean_undergraduate] = (
        "explicit_undergraduate_batch_or_no_vocational_registration"
    )

    explicit_registered_ug_batch = (
        undergraduate_batch
        & institution_level.eq("本科")
        & registered
    )
    level.loc[explicit_registered_ug_batch] = "undergraduate"
    reason.loc[explicit_registered_ug_batch] = (
        "explicit_undergraduate_batch_despite_vocational_offer"
    )

    ambiguous_dual = (
        ~vocational
        & ~undergraduate_batch
        & institution_level.eq("本科")
        & registered
    )
    level.loc[ambiguous_dual] = "ambiguous_dual_offer"
    reason.loc[ambiguous_dual] = (
        "ambiguous_batch_and_three_year_program_registered"
    )

    unresolved = institution_level.eq("unresolved")
    level.loc[unresolved] = "unresolved"
    reason.loc[unresolved] = "institution_not_mapped"

    result = pd.DataFrame(
        {
            "batch_level_hint": pd.Series(
                "ambiguous",
                index=frame.index,
            )
            .mask(batch.str.contains(EXPLICIT_VOCATIONAL_BATCH), "vocational")
            .mask(undergraduate_batch, "undergraduate"),
            "program_degree_level": level,
            "program_level_reason": reason,
        },
        index=frame.index,
    )
    result["program_level_evidence_url"] = ""
    result["program_level_evidence_note"] = ""

    if "manual_program_degree_level" in frame.columns:
        manual_level = frame["manual_program_degree_level"].fillna("")
        manual_mask = manual_level.isin(
            ["undergraduate", "vocational_three_year"]
        )
        result.loc[manual_mask, "program_degree_level"] = manual_level.loc[
            manual_mask
        ]
        result.loc[
            manual_mask, "program_level_reason"
        ] = "manual_admission_plan_override"
        result.loc[
            manual_mask, "program_level_evidence_url"
        ] = frame.loc[manual_mask, "manual_evidence_url"].fillna("")
        result.loc[
            manual_mask, "program_level_evidence_note"
        ] = frame.loc[manual_mask, "manual_evidence_note"].fillna("")
    return result


def classify_count_definition(frame: pd.DataFrame) -> pd.Series:
    definition = pd.Series(
        "reported_count_definition_not_verified",
        index=frame.index,
        dtype="object",
    )
    definition.loc[frame["admit_count"].isna()] = "not_reported"
    definition.loc[
        frame["year"].eq(2026)
        & frame["province"].eq("浙江")
        & frame["admit_count"].notna()
    ] = "planned_places"
    definition.loc[
        frame["year"].eq(2026)
        & frame["province"].eq("贵州")
        & frame["admit_count"].notna()
    ] = "filed_candidates"
    return definition


def build_eligibility_flags(frame: pd.DataFrame) -> pd.DataFrame:
    plan = classify_plan_type(frame)
    program = classify_program_level(frame)
    fields = pd.concat([plan, program], axis=1)
    fields["count_definition"] = classify_count_definition(frame)
    fields["source_count_value"] = frame["admit_count"]

    undergraduate = fields["program_degree_level"].eq("undergraduate")
    ordinary = fields["admission_plan_type"].eq("ordinary_regular")
    fields["primary_eligible_candidate"] = (
        undergraduate & ordinary & ~fields["sino_foreign"]
    )
    fields["primary_with_sino_foreign_candidate"] = undergraduate & (
        ordinary | fields["admission_plan_type"].eq("sino_foreign")
    )

    reasons = []
    for row in fields.itertuples(index=False):
        row_reasons = []
        if row.program_degree_level == "vocational_three_year":
            row_reasons.append("vocational_three_year")
        elif row.program_degree_level == "ambiguous_dual_offer":
            row_reasons.append("ambiguous_program_level")
        elif row.program_degree_level == "unresolved":
            row_reasons.append("institution_unresolved")
        if row.admission_plan_type != "ordinary_regular":
            row_reasons.append(row.admission_plan_type)
        if row.sino_foreign:
            row_reasons.append("sino_foreign")
        reasons.append("|".join(dict.fromkeys(row_reasons)))
    fields["eligibility_exclusion_reason"] = reasons
    return fields


def scenario_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    undergraduate = frame["program_degree_level"].eq("undergraduate")
    ambiguous = frame["program_degree_level"].eq("ambiguous_dual_offer")
    ordinary = frame["admission_plan_type"].eq("ordinary_regular")
    primary = frame["primary_eligible_candidate"]
    exact_unique = ~frame.duplicated()
    business_unique = ~frame.duplicated(DEDUP_KEY)
    return {
        "current_all_clinical": pd.Series(True, index=frame.index),
        "exclude_special_entry": ~frame["special_entry"],
        "undergraduate_program_only": undergraduate,
        "ordinary_undergraduate_primary": primary,
        "ordinary_undergraduate_primary_exact_deduplicated": (
            primary & exact_unique
        ),
        "ordinary_undergraduate_primary_business_key_deduplicated": (
            primary & business_unique
        ),
        "ordinary_undergraduate_ambiguous_upper_bound": (
            (undergraduate | ambiguous) & ordinary & ~frame["sino_foreign"]
        ),
        "ordinary_undergraduate_with_sino_foreign": frame[
            "primary_with_sino_foreign_candidate"
        ],
    }


def summarize_scenarios(
    frame: pd.DataFrame, masks: dict[str, pd.Series]
) -> pd.DataFrame:
    rows = []
    for scenario, keep in masks.items():
        selected = frame[keep].copy()
        school_layer, province_layer = analysis.build_analysis_layer(selected)
        admission_recent = analysis.build_recent_balanced_change(
            school_layer, province_layer
        )
        candidate_recent = analysis.build_recent_balanced_change(
            school_layer,
            province_layer,
            metric="candidate_percentile",
        )
        admission_all = admission_recent[
            admission_recent["track"].eq("all_clinical")
            & admission_recent["comparison_eligible"]
        ]
        admission_five = admission_recent[
            admission_recent["track"].eq("five_year")
            & admission_recent["comparison_eligible"]
        ]
        admission_eight = admission_recent[
            admission_recent["track"].eq("eight_year")
            & admission_recent["comparison_eligible"]
        ]
        candidate_all = candidate_recent[
            candidate_recent["track"].eq("all_clinical")
            & candidate_recent["comparison_eligible"]
        ]
        rows.append(
            {
                "scenario": scenario,
                "records_included": len(selected),
                "records_excluded": int((~keep).sum()),
                "recent_eligible_provinces_all_clinical": (
                    admission_all["province"].nunique()
                ),
                "recent_eligible_provinces_five_year": (
                    admission_five["province"].nunique()
                ),
                "recent_eligible_provinces_eight_year": (
                    admission_eight["province"].nunique()
                ),
                "mean_all_change_all_clinical": admission_all[
                    "all_change"
                ].mean(),
                "median_all_change_all_clinical": admission_all[
                    "all_change"
                ].median(),
                "mean_balanced_change_all_clinical": admission_all[
                    "balanced_change"
                ].mean(),
                "median_balanced_change_all_clinical": admission_all[
                    "balanced_change"
                ].median(),
                "candidate_eligible_provinces_all_clinical": (
                    candidate_all["province"].nunique()
                ),
                "candidate_mean_all_change_all_clinical": candidate_all[
                    "all_change"
                ].mean(),
                "candidate_median_all_change_all_clinical": candidate_all[
                    "all_change"
                ].median(),
                "candidate_mean_balanced_change_all_clinical": (
                    candidate_all["balanced_change"].mean()
                ),
                "candidate_median_balanced_change_all_clinical": (
                    candidate_all["balanced_change"].median()
                ),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    panel = pd.read_csv(PANEL, low_memory=False)
    panel = panel[
        panel["subject"].eq("clinical")
        & panel["university"].fillna("").astype(str).ne("")
    ].copy()
    panel["university"] = (
        panel["university"].fillna("").astype(str).str.strip()
    )

    institutions = load_institution_registry()
    vocational = load_vocational_registry()
    matches = build_institution_matches(panel, institutions)

    enriched = panel.merge(
        matches,
        left_on=["university", "year"],
        right_on=["university", "admission_year"],
        how="left",
        validate="many_to_one",
    )
    enriched = enriched.merge(
        vocational[
            [
                "registry_year",
                "school_code",
                "registered_school_name",
                "program_duration_years",
            ]
        ].rename(columns={"registry_year": "year"}),
        on=["year", "school_code"],
        how="left",
        validate="many_to_one",
    )
    enriched["vocational_clinical_registered"] = enriched[
        "registered_school_name"
    ].notna()

    manual_overrides = pd.read_csv(
        MANUAL_OVERRIDES,
        low_memory=False,
    ).fillna("")
    manual_overrides = manual_overrides.rename(
        columns={
            "program_degree_level": "manual_program_degree_level",
            "evidence_url": "manual_evidence_url",
            "evidence_note": "manual_evidence_note",
        }
    )
    enriched = enriched.merge(
        manual_overrides[
            [
                "year",
                "province",
                "university",
                "manual_program_degree_level",
                "manual_evidence_url",
                "manual_evidence_note",
            ]
        ],
        on=["year", "province", "university"],
        how="left",
        validate="many_to_one",
    )

    fields = build_eligibility_flags(enriched)
    enriched = pd.concat([enriched, fields], axis=1)

    matches.to_csv(INSTITUTION_REGISTRY, index=False, encoding="utf-8-sig")
    vocational.to_csv(VOCATIONAL_REGISTRY, index=False, encoding="utf-8-sig")
    fields.to_csv(ELIGIBILITY_FIELDS, index=False, encoding="utf-8-sig")
    enriched.to_csv(ENRICHED_PANEL, index=False, encoding="utf-8-sig")

    summary = summarize_scenarios(enriched, scenario_masks(enriched))
    summary.to_csv(SENSITIVITY, index=False, encoding="utf-8-sig")

    summary_json = {
        "panel_rows": len(enriched),
        "institution_year_pairs": len(matches),
        "vocational_registry_rows": len(vocational),
        "match_status_counts": (
            matches["match_status"].value_counts().sort_index().to_dict()
        ),
        "program_degree_level_counts": (
            enriched["program_degree_level"].value_counts().to_dict()
        ),
        "manual_program_level_overrides_applied": int(
            enriched["program_level_reason"]
            .eq("manual_admission_plan_override")
            .sum()
        ),
        "admission_plan_type_counts": (
            enriched["admission_plan_type"].value_counts().to_dict()
        ),
        "count_definition_counts": (
            enriched["count_definition"].value_counts().to_dict()
        ),
        "primary_eligible_candidate_rows": int(
            enriched["primary_eligible_candidate"].sum()
        ),
        "recent_sensitivity_rows": summary.to_dict(orient="records"),
    }
    SUMMARY.write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Wrote {len(matches):,} institution-year matches")
    print(f"Wrote {len(vocational):,} vocational clinical registrations")
    print(f"Wrote {len(enriched):,} enriched panel rows")
    print(
        summary[
            [
                "scenario",
                "records_excluded",
                "recent_eligible_provinces_all_clinical",
                "mean_all_change_all_clinical",
                "mean_balanced_change_all_clinical",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
