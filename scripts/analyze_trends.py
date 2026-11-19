"""Build the clinical-medicine analysis layer and exploratory figures.

The source panel contains both clinical-medicine and engineering records from
the historical collection phase. This script keeps only clinical records.
Source tiers are retained as provenance flags, but the 2026 official and
public-archive records enter the same province-year analysis.
"""

from __future__ import annotations

import math
import random
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
FIGURES = OUTPUT / "figures"
REPORT_FIGURES = OUTPUT / "report_figures"
INPUT = OUTPUT / "clinical_panel_2017_2026_candidate_percentile.csv"

YEARS = list(range(2017, 2027))
RECENT_BALANCED_YEARS = (2025, 2026)
LONG_BALANCED_YEARS = tuple(range(2021, 2027))
CLINICAL_TRACKS = ("all_clinical", "five_year", "eight_year")
MIN_SCHOOLS = 3
BOOTSTRAP_REPLICATES = 2000
RANDOM_SEED = 20261117
CORE_REPORT_FIGURES = [
    "fig_heatmap_all_clinical.png",
    "fig_average_curves.png",
    "fig_annual_changes.png",
    "fig_balanced_change_2025_2026.png",
    "fig_school_change_distribution_2025_2026.png",
    "fig_cumulative_change_2021_2026.png",
    "fig_track_premium.png",
    "fig_school_tier_gradient_2025_2026.png",
]
DEEP_BLUE = "#0b5c8e"
MUTED_BLUE = "#4b85ab"
MUTED_BROWN = "#a5785f"
WARM_SAND = "#be9876"
LIGHT_BLUE = "#7fa9c6"
GRID_COLOR = "#e5e7eb"
NOTE_COLOR = "#4b5563"
NO_DATA_COLOR = "#d7dadd"
LEVEL_CMAP = LinearSegmentedColormap.from_list(
    "clinical_level",
    ["#f7fbfe", "#c7e0ee", "#6aa6c8", "#2777a5", "#083a5a"],
)
CHANGE_CMAP = LinearSegmentedColormap.from_list(
    "clinical_change",
    ["#9b6a52", "#f7f4f1", "#0b5c8e"],
)

PROVINCE_ORDER = [
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
]

TRACKS = {
    "all_clinical": {
        "label": "临床医学（全部）",
        "short_label": "全部临床",
        "color": "#1f5a7a",
    },
    "five_year": {
        "label": "临床医学（五年制）",
        "short_label": "五年制",
        "color": "#2a9d8f",
    },
    "eight_year": {
        "label": "临床医学（八年制）",
        "short_label": "八年制",
        "color": "#b56576",
    },
}

METRICS = {
    "admission_percentile": {
        "label": "专业池录取百分位",
        "short_label": "专业池百分位",
    },
    "candidate_percentile": {
        "label": "考生位次百分位",
        "short_label": "考生分布百分位",
    },
}


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.family": "Microsoft YaHei",
            "axes.unicode_minus": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#4b5563",
            "axes.labelcolor": "#111827",
            "text.color": "#111827",
            "xtick.color": "#374151",
            "ytick.color": "#374151",
            "axes.titleweight": "bold",
            "font.size": 13,
            "axes.titlesize": 16,
            "axes.labelsize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
        }
    )


def read_panel() -> pd.DataFrame:
    usecols = [
        "province",
        "year",
        "subject",
        "clinical_track",
        "university",
        "major",
        "admission_percentile",
        "candidate_percentile",
        "source_tier",
        "analysis_layer",
        "data_scope",
    ]
    frame = pd.read_csv(
        INPUT,
        usecols=usecols,
        dtype={
            "province": "string",
            "year": "int64",
            "subject": "string",
            "clinical_track": "string",
            "university": "string",
            "major": "string",
            "source_tier": "string",
            "analysis_layer": "string",
            "data_scope": "string",
        },
    )
    for metric in METRICS:
        frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame["source_tier"] = frame["source_tier"].fillna("unknown")
    frame["analysis_layer"] = frame["analysis_layer"].fillna("unknown")
    frame["data_scope"] = frame["data_scope"].fillna("unknown")
    frame["university"] = frame["university"].fillna("").str.strip()
    frame = frame[
        frame["subject"].eq("clinical") & frame["university"].ne("")
    ].copy()
    return frame


def track_mask(frame: pd.DataFrame, track: str) -> pd.Series:
    if track == "all_clinical":
        return frame["subject"].eq("clinical")
    if track == "five_year":
        return frame["subject"].eq("clinical") & frame["clinical_track"].isin(
            ["explicit_five_year", "ordinary_five_year_likely"]
        )
    if track == "eight_year":
        return frame["subject"].eq("clinical") & frame[
            "clinical_track"
        ].eq("explicit_eight_year")
    raise ValueError(f"Unknown track: {track}")


def combine_values(values: pd.Series) -> str:
    clean = sorted(
        {
            str(value)
            for value in values
            if pd.notna(value) and str(value).strip() and str(value) != "nan"
        }
    )
    return "|".join(clean) if clean else "unknown"


def source_group(source_tiers: str, year: int) -> str:
    tiers = set(filter(None, source_tiers.split("|")))
    if year == 2026:
        official = any(tier.startswith("A_") for tier in tiers)
        archive = any(tier.startswith("B_") for tier in tiers)
        if official and archive:
            return "A+B"
        if official:
            return "A"
        if archive:
            return "B"
        return "other"
    if tiers and all(tier.startswith("A_") for tier in tiers):
        return "A"
    if any(tier.startswith("B_") for tier in tiers):
        return "B"
    return "other"


def aggregate_metric(
    frame: pd.DataFrame, track: str, metric: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = frame[track_mask(frame, track) & frame[metric].notna()].copy()
    selected["source_tier"] = selected["source_tier"].fillna("unknown")

    school_groups = selected.groupby(
        ["province", "year", "university"], dropna=False
    )
    school = school_groups.agg(
        school_value=(metric, "median"),
        n_records=(metric, "size"),
        source_tiers=("source_tier", combine_values),
        analysis_layers=("analysis_layer", combine_values),
        data_scopes=("data_scope", combine_values),
    ).reset_index()
    school["source_group"] = school.apply(
        lambda row: source_group(row["source_tiers"], int(row["year"])), axis=1
    )

    province_groups = school.groupby(["province", "year"], dropna=False)
    province = province_groups.agg(
        value=("school_value", "median"),
        n_schools=("university", "nunique"),
        n_records=("n_records", "sum"),
        school_p25=("school_value", lambda values: values.quantile(0.25)),
        school_p75=("school_value", lambda values: values.quantile(0.75)),
        source_tiers=("source_tiers", combine_values),
        analysis_layers=("analysis_layers", combine_values),
        data_scopes=("data_scopes", combine_values),
    ).reset_index()
    province["source_group"] = province.apply(
        lambda row: source_group(row["source_tiers"], int(row["year"])), axis=1
    )
    province["track"] = track
    province["track_label"] = TRACKS[track]["label"]
    province["metric"] = metric
    province["metric_label"] = METRICS[metric]["label"]
    province["meets_min_schools"] = province["n_schools"].ge(MIN_SCHOOLS)
    province["is_2026"] = province["year"].eq(2026)
    return school, province


def build_analysis_layer(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_school = []
    all_province = []
    for track in TRACKS:
        for metric in METRICS:
            school, province = aggregate_metric(frame, track, metric)
            school["metric"] = metric
            school["metric_label"] = METRICS[metric]["label"]
            school["track"] = track
            school["track_label"] = TRACKS[track]["label"]
            all_school.append(school)
            all_province.append(province)

    school_output = pd.concat(all_school, ignore_index=True)
    province_output = pd.concat(all_province, ignore_index=True)
    school_output = school_output.sort_values(
        ["track", "metric", "province", "year", "university"]
    )
    province_output = province_output.sort_values(
        ["track", "metric", "province", "year"]
    )
    return school_output, province_output


def build_recent_balanced_change(
    school_layer: pd.DataFrame,
    province_layer: pd.DataFrame,
    metric: str = "admission_percentile",
) -> pd.DataFrame:
    school = school_layer[
        school_layer["metric"].eq(metric)
        & school_layer["school_value"].notna()
    ].copy()
    province = province_layer[
        province_layer["metric"].eq(metric)
        & province_layer["meets_min_schools"]
    ].copy()
    rows = []

    for track in CLINICAL_TRACKS:
        track_school = school[school["track"].eq(track)]
        school_matrix = track_school.pivot_table(
            index=["province", "university"],
            columns="year",
            values="school_value",
            aggfunc="median",
        )
        available_years = [
            year for year in RECENT_BALANCED_YEARS if year in school_matrix.columns
        ]
        if len(available_years) != len(RECENT_BALANCED_YEARS):
            continue

        common_schools = school_matrix.dropna(
            subset=list(RECENT_BALANCED_YEARS)
        ).reset_index()
        balanced = common_schools.groupby("province").agg(
            balanced_2025=(2025, "median"),
            balanced_2026=(2026, "median"),
            n_schools_balanced=("university", "nunique"),
        )
        balanced["balanced_change"] = (
            balanced["balanced_2026"] - balanced["balanced_2025"]
        )

        track_province = province[province["track"].eq(track)]
        all_values = track_province.pivot(
            index="province", columns="year", values="value"
        )
        all_counts = track_province.pivot(
            index="province", columns="year", values="n_schools"
        )
        source_2026 = (
            track_province[track_province["year"].eq(2026)]
            .set_index("province")["source_group"]
        )
        provinces = sorted(set(all_values.index) | set(balanced.index))
        for province_name in provinces:
            all_2025 = (
                all_values.at[province_name, 2025]
                if province_name in all_values.index and 2025 in all_values.columns
                else math.nan
            )
            all_2026 = (
                all_values.at[province_name, 2026]
                if province_name in all_values.index and 2026 in all_values.columns
                else math.nan
            )
            row = (
                balanced.loc[province_name]
                if province_name in balanced.index
                else pd.Series(dtype=float)
            )
            balanced_2025 = row.get("balanced_2025", math.nan)
            balanced_2026 = row.get("balanced_2026", math.nan)
            n_balanced = row.get("n_schools_balanced", 0)
            all_change = (
                all_2026 - all_2025
                if pd.notna(all_2025) and pd.notna(all_2026)
                else math.nan
            )
            balanced_change = (
                balanced_2026 - balanced_2025
                if pd.notna(balanced_2025) and pd.notna(balanced_2026)
                else math.nan
            )
            rows.append(
                {
                    "track": track,
                    "track_label": TRACKS[track]["label"],
                    "province": province_name,
                    "all_2025": all_2025,
                    "all_2026": all_2026,
                    "all_change": all_change,
                    "n_schools_all_2025": (
                        all_counts.at[province_name, 2025]
                        if province_name in all_counts.index
                        and 2025 in all_counts.columns
                        else math.nan
                    ),
                    "n_schools_all_2026": (
                        all_counts.at[province_name, 2026]
                        if province_name in all_counts.index
                        and 2026 in all_counts.columns
                        else math.nan
                    ),
                    "balanced_2025": balanced_2025,
                    "balanced_2026": balanced_2026,
                    "balanced_change": balanced_change,
                    "n_schools_balanced": int(n_balanced)
                    if pd.notna(n_balanced)
                    else 0,
                    "comparison_eligible": (
                        pd.notna(all_change)
                        and pd.notna(balanced_change)
                        and n_balanced >= MIN_SCHOOLS
                    ),
                    "composition_gap": (
                        all_change - balanced_change
                        if pd.notna(all_change) and pd.notna(balanced_change)
                        else math.nan
                    ),
                    "source_group_2026": source_2026.get(province_name, ""),
                }
            )

    return pd.DataFrame(rows)


def build_long_balanced_panel(
    school_layer: pd.DataFrame, province_layer: pd.DataFrame
) -> pd.DataFrame:
    school = school_layer[
        school_layer["metric"].eq("admission_percentile")
        & school_layer["school_value"].notna()
        & school_layer["year"].isin(LONG_BALANCED_YEARS)
    ].copy()
    province = province_layer[
        province_layer["metric"].eq("admission_percentile")
        & province_layer["meets_min_schools"]
        & province_layer["year"].isin(LONG_BALANCED_YEARS)
    ].copy()
    rows = []

    for track in CLINICAL_TRACKS:
        track_school = school[school["track"].eq(track)]
        presence = (
            track_school.groupby(["province", "university"])["year"]
            .nunique()
            .rename("n_years")
            .reset_index()
        )
        common_schools = presence[
            presence["n_years"].eq(len(LONG_BALANCED_YEARS))
        ][["province", "university"]]
        balanced_schools = track_school.merge(
            common_schools, on=["province", "university"], how="inner"
        )
        balanced = (
            balanced_schools.groupby(["province", "year"])
            .agg(
                balanced_value=("school_value", "median"),
                balanced_n_schools=("university", "nunique"),
                source_group=("source_group", combine_values),
            )
            .reset_index()
        )
        balanced = balanced[
            balanced["balanced_n_schools"].ge(MIN_SCHOOLS)
        ].copy()
        complete_provinces = (
            balanced.groupby("province")["year"]
            .nunique()
            .loc[lambda values: values.eq(len(LONG_BALANCED_YEARS))]
            .index
        )
        balanced = balanced[balanced["province"].isin(complete_provinces)]

        track_province = province[
            province["track"].eq(track)
            & province["province"].isin(complete_provinces)
        ]
        all_values = track_province[
            ["province", "year", "value", "n_schools", "source_group"]
        ].rename(
            columns={
                "value": "all_value",
                "n_schools": "all_n_schools",
                "source_group": "all_source_group",
            }
        )
        merged = balanced.merge(
            all_values, on=["province", "year"], how="inner"
        ).sort_values(["province", "year"])
        merged["track"] = track
        merged["track_label"] = TRACKS[track]["label"]
        rows.append(merged)

    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_track_premium(
    province_layer: pd.DataFrame, school_layer: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    province = province_layer[
        province_layer["metric"].eq("admission_percentile")
        & province_layer["meets_min_schools"]
        & province_layer["track"].isin(["five_year", "eight_year"])
    ]
    province_pair = province.pivot_table(
        index=["province", "year"],
        columns="track",
        values="value",
        aggfunc="first",
    ).dropna(subset=["five_year", "eight_year"])
    province_pair = province_pair.rename(
        columns={"five_year": "five_year_value", "eight_year": "eight_year_value"}
    ).reset_index()
    province_pair["track_gap"] = (
        province_pair["eight_year_value"] - province_pair["five_year_value"]
    )

    school = school_layer[
        school_layer["metric"].eq("admission_percentile")
        & school_layer["school_value"].notna()
        & school_layer["track"].isin(["five_year", "eight_year"])
    ]
    school_pair = school.pivot_table(
        index=["province", "year", "university"],
        columns="track",
        values="school_value",
        aggfunc="median",
    ).dropna(subset=["five_year", "eight_year"])
    school_pair = school_pair.rename(
        columns={"five_year": "five_year_value", "eight_year": "eight_year_value"}
    ).reset_index()
    school_pair["track_gap"] = (
        school_pair["eight_year_value"] - school_pair["five_year_value"]
    )
    return province_pair, school_pair


def build_school_change_pairs(
    school_layer: pd.DataFrame, balanced_recent: pd.DataFrame
) -> pd.DataFrame:
    school = school_layer[
        school_layer["metric"].eq("admission_percentile")
        & school_layer["school_value"].notna()
        & school_layer["year"].isin(RECENT_BALANCED_YEARS)
        & school_layer["track"].isin(CLINICAL_TRACKS)
    ].copy()
    rows = []
    for track in CLINICAL_TRACKS:
        eligible_provinces = set(
            balanced_recent.loc[
                balanced_recent["track"].eq(track)
                & balanced_recent["comparison_eligible"],
                "province",
            ]
        )
        subset = school[
            school["track"].eq(track)
            & school["province"].isin(eligible_provinces)
        ]
        wide = (
            subset.pivot_table(
                index=["province", "university"],
                columns="year",
                values="school_value",
                aggfunc="median",
            )
            .dropna(subset=list(RECENT_BALANCED_YEARS))
            .rename(
                columns={
                    2025: "value_2025",
                    2026: "value_2026",
                }
            )
            .reset_index()
        )
        source = (
            subset[subset["year"].eq(2026)][
                ["province", "university", "source_group"]
            ]
            .drop_duplicates(["province", "university"])
            .rename(columns={"source_group": "source_group_2026"})
        )
        wide = wide.merge(source, on=["province", "university"], how="left")
        wide["track"] = track
        wide["track_label"] = TRACKS[track]["label"]
        wide["change"] = wide["value_2026"] - wide["value_2025"]
        rows.append(wide)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_school_count_change(balanced_recent: pd.DataFrame) -> pd.DataFrame:
    subset = balanced_recent[
        balanced_recent["track"].isin(CLINICAL_TRACKS)
        & balanced_recent["comparison_eligible"]
    ].copy()
    subset["school_count_change"] = (
        subset["n_schools_all_2026"] - subset["n_schools_all_2025"]
    )
    subset["school_count_change_pct"] = (
        subset["school_count_change"] / subset["n_schools_all_2025"] * 100
    )
    return subset[
        [
            "track",
            "track_label",
            "province",
            "source_group_2026",
            "n_schools_all_2025",
            "n_schools_all_2026",
            "school_count_change",
            "school_count_change_pct",
        ]
    ].copy()


def build_leave_one_out(
    balanced_recent: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for track in CLINICAL_TRACKS:
        subset = balanced_recent[
            balanced_recent["track"].eq(track)
            & balanced_recent["comparison_eligible"]
        ]
        for outcome in ["all_change", "balanced_change"]:
            values = subset[outcome]
            full_mean = float(values.mean())
            for index, row in subset.iterrows():
                remaining = values.drop(index=index)
                lovo_mean = float(remaining.mean())
                rows.append(
                    {
                        "track": track,
                        "track_label": TRACKS[track]["label"],
                        "outcome": outcome,
                        "excluded_province": row["province"],
                        "source_group_2026": row["source_group_2026"],
                        "n_provinces_full": int(len(subset)),
                        "full_mean": full_mean,
                        "lovo_mean": lovo_mean,
                        "difference_from_full": lovo_mean - full_mean,
                    }
                )
    return pd.DataFrame(rows)


def build_school_tier_change(
    school_change_pairs: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    tier_labels = ["低位", "中位", "高位"]
    for track in CLINICAL_TRACKS:
        subset = school_change_pairs[
            school_change_pairs["track"].eq(track)
        ].copy()

        def assign_tier(group: pd.DataFrame) -> pd.Series:
            if len(group) < 6:
                return pd.Series(index=group.index, dtype="object")
            ranks = group["value_2025"].rank(method="first")
            return pd.qcut(ranks, q=3, labels=tier_labels)

        subset["tier"] = subset.groupby("province", group_keys=False).apply(
            assign_tier
        )
        subset = subset.dropna(subset=["tier"])
        grouped = (
            subset.groupby(["province", "tier"], observed=True)["change"]
            .agg(
                n_schools="size",
                median_change="median",
                mean_change="mean",
            )
            .reset_index()
        )
        grouped["tier"] = grouped["tier"].astype(str)
        grouped["tier_order"] = grouped["tier"].map(
            {label: index for index, label in enumerate(tier_labels)}
        )
        grouped["track"] = track
        grouped["track_label"] = TRACKS[track]["label"]
        rows.append(grouped)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def build_cumulative_change(
    balanced_long: pd.DataFrame,
) -> pd.DataFrame:
    subset = balanced_long[balanced_long["track"].isin(CLINICAL_TRACKS)].copy()
    baseline = (
        subset[subset["year"].eq(2021)]
        .set_index(["track", "province"])["balanced_value"]
        .rename("baseline_2021")
    )
    subset = subset.merge(
        baseline,
        left_on=["track", "province"],
        right_index=True,
        how="left",
    )
    subset["cumulative_change"] = (
        subset["balanced_value"] - subset["baseline_2021"]
    )
    return subset[
        [
            "track",
            "track_label",
            "province",
            "year",
            "balanced_value",
            "baseline_2021",
            "cumulative_change",
        ]
    ].copy()


def build_track_coverage(province_layer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track in TRACKS:
        metric_rows = province_layer[
            (province_layer["track"] == track)
            & (province_layer["metric"] == "admission_percentile")
        ]
        school_rows = province_layer[
            (province_layer["track"] == track)
            & (province_layer["metric"] == "admission_percentile")
        ]
        for year in YEARS:
            one_year = metric_rows[metric_rows["year"] == year]
            eligible = one_year[one_year["meets_min_schools"]]
            rows.append(
                {
                    "track": track,
                    "track_label": TRACKS[track]["label"],
                    "year": year,
                    "province_cells_any": len(one_year),
                    "province_cells_min_schools": len(eligible),
                    "school_province_pairs": int(
                        school_rows[school_rows["year"] == year]["n_schools"].sum()
                    ),
                    "records": int(
                        metric_rows[metric_rows["year"] == year]["n_records"].sum()
                    ),
                }
            )
    return pd.DataFrame(rows)


def bootstrap_mean_ci(
    values: np.ndarray, replicates: int, rng: random.Random
) -> tuple[float, float, float]:
    clean = values[np.isfinite(values)]
    if clean.size == 0:
        return (math.nan, math.nan, math.nan)
    mean = float(clean.mean())
    if clean.size == 1:
        return (mean, mean, mean)
    draws = np.empty(replicates, dtype=float)
    n = clean.size
    for index in range(replicates):
        sample = np.fromiter(
            (clean[rng.randrange(n)] for _ in range(n)),
            dtype=float,
            count=n,
        )
        draws[index] = sample.mean()
    low, high = np.quantile(draws, [0.025, 0.975])
    return (mean, float(low), float(high))


def build_curve_summary(province_layer: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(RANDOM_SEED)
    rows = []
    for track in TRACKS:
        for metric in METRICS:
            subset = province_layer[
                (province_layer["track"] == track)
                & (province_layer["metric"] == metric)
                & (province_layer["meets_min_schools"])
            ]
            for year in YEARS:
                values = subset[subset["year"] == year]["value"].to_numpy(dtype=float)
                mean, low, high = bootstrap_mean_ci(
                    values, BOOTSTRAP_REPLICATES, rng
                )
                rows.append(
                    {
                        "track": track,
                        "track_label": TRACKS[track]["label"],
                        "metric": metric,
                        "metric_label": METRICS[metric]["label"],
                        "year": year,
                        "n_provinces": int(np.isfinite(values).sum()),
                        "mean": mean,
                        "ci_low": low,
                        "ci_high": high,
                        "median_across_provinces": (
                            float(np.nanmedian(values)) if values.size else math.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def heatmap_matrices(
    province_layer: pd.DataFrame, track: str, metric: str
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    subset = province_layer[
        (province_layer["track"] == track) & (province_layer["metric"] == metric)
    ].copy()
    value = subset.pivot(index="province", columns="year", values="value")
    count = subset.pivot(index="province", columns="year", values="n_schools")
    source = subset.pivot(index="province", columns="year", values="source_group")
    value = value.reindex(index=PROVINCE_ORDER, columns=YEARS)
    count = count.reindex(index=PROVINCE_ORDER, columns=YEARS)
    source = source.reindex(index=PROVINCE_ORDER, columns=YEARS)
    # Use a stable administrative order. Missing combinations stay missing.
    return value, count, source


def draw_heatmap_panel(
    ax: plt.Axes,
    matrix: pd.DataFrame,
    count: pd.DataFrame,
    source: pd.DataFrame,
    title: str,
    cmap: str,
    norm: Normalize | TwoSlopeNorm,
    colorbar_label: str,
) -> None:
    values = matrix.to_numpy(dtype=float)
    cmap_object = cmap.copy() if hasattr(cmap, "copy") else plt.get_cmap(cmap).copy()
    cmap_object.set_bad(NO_DATA_COLOR)
    image = ax.imshow(
        np.ma.masked_invalid(values),
        aspect="auto",
        cmap=cmap_object,
        norm=norm,
        interpolation="nearest",
    )
    coverage = count.notna().sum(axis=0).reindex(YEARS).fillna(0).astype(int)
    ax.set_xticks(
        np.arange(len(YEARS)),
        [f"{year}\nn={coverage.loc[year]}" for year in YEARS],
    )
    ax.set_yticks(np.arange(len(matrix.index)), matrix.index)
    ax.tick_params(axis="x", labelsize=12.5, length=0)
    ax.tick_params(axis="y", labelsize=12, length=0)
    ax.set_xticks(np.arange(-0.5, len(YEARS), 1), minor=True)
    ax.set_yticks(np.arange(-0.5, len(matrix.index), 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=0.65)
    ax.tick_params(which="minor", bottom=False, left=False)
    ax.set_title(title, loc="left", fontsize=18, pad=10)
    for row_index, province in enumerate(matrix.index):
        for column_index, year in enumerate(YEARS):
            if (
                pd.notna(matrix.loc[province, year])
                and pd.notna(count.loc[province, year])
                and count.loc[province, year] < MIN_SCHOOLS
            ):
                ax.add_patch(
                    Rectangle(
                        (column_index - 0.5, row_index - 0.5),
                        1,
                        1,
                        fill=False,
                        hatch="///",
                        edgecolor="#1f2937",
                        linewidth=0.45,
                    )
                )
    colorbar = plt.colorbar(image, ax=ax, fraction=0.035, pad=0.035)
    colorbar.ax.set_title(
        colorbar_label,
        fontsize=11.5,
        linespacing=1.25,
        pad=7,
    )
    colorbar.ax.tick_params(labelsize=11)


def write_heatmap_data(
    track: str, metric: str, value: pd.DataFrame, count: pd.DataFrame, source: pd.DataFrame
) -> None:
    path = OUTPUT / f"analysis_heatmap_{track}_{metric}.csv"
    rows = []
    for province in value.index:
        baseline = value.loc[province, 2017] if 2017 in value.columns else math.nan
        observed = value.loc[province].dropna()
        first_year = int(observed.index[0]) if not observed.empty else math.nan
        first_value = float(observed.iloc[0]) if not observed.empty else math.nan
        for year in YEARS:
            current = value.loc[province, year]
            rows.append(
                {
                    "track": track,
                    "track_label": TRACKS[track]["label"],
                    "metric": metric,
                    "province": province,
                    "year": year,
                    "value": current,
                    "delta_from_2017": (
                        current - baseline if pd.notna(current) and pd.notna(baseline) else math.nan
                    ),
                    "first_available_year": first_year,
                    "first_available_value": first_value,
                    "change_from_first_available": (
                        current - first_value
                        if pd.notna(current) and pd.notna(first_value)
                        else math.nan
                    ),
                    "n_schools": count.loc[province, year],
                    "source_group": source.loc[province, year],
                    "meets_min_schools": pd.notna(count.loc[province, year])
                    and count.loc[province, year] >= MIN_SCHOOLS,
                }
            )
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def draw_heatmaps(province_layer: pd.DataFrame) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    plt.rcParams["axes.titleweight"] = "bold"
    for track in CLINICAL_TRACKS:
        value, count, source = heatmap_matrices(
            province_layer, track, "admission_percentile"
        )
        write_heatmap_data(track, "admission_percentile", value, count, source)
        first_values = value.apply(
            lambda row: row.dropna().iloc[0] if row.notna().any() else math.nan,
            axis=1,
        )
        deltas = value.sub(first_values, axis=0)
        first_available_mask = value.notna() & value.notna().cumsum(axis=1).eq(1)
        deltas = deltas.mask(first_available_mask, 0.0)

        fig, axes = plt.subplots(
            1,
            2,
            figsize=(16.5, 11.8),
            gridspec_kw={"width_ratios": [1.2, 1.05], "wspace": 0.20},
        )
        draw_heatmap_panel(
            axes[0],
            value,
            count,
            source,
            "录取百分位水平",
            LEVEL_CMAP,
            Normalize(vmin=0, vmax=100),
            "百分位",
        )
        delta_cap = 30.0
        draw_heatmap_panel(
            axes[1],
            deltas,
            count,
            source,
            "相对首个可用年份变化",
            CHANGE_CMAP,
            TwoSlopeNorm(vmin=-delta_cap, vcenter=0, vmax=delta_cap),
            "百分点",
        )
        fig.suptitle(
            f"{TRACKS[track]['label']}：2017–2026 省级录取位置",
            x=0.06,
            y=0.985,
            ha="left",
            fontsize=22,
            fontweight="bold",
        )
        legend_handles = [
            Patch(
                facecolor=LEVEL_CMAP(0.88),
                edgecolor="white",
                label="颜色越深：百分位越高",
            ),
            Patch(facecolor=NO_DATA_COLOR, edgecolor="white", label="无专业池记录"),
            Patch(
                facecolor="white",
                edgecolor="#374151",
                hatch="///",
                label="有效院校少于 3 所",
            ),
        ]
        fig.legend(
            handles=legend_handles,
            loc="lower left",
            bbox_to_anchor=(0.06, 0.045),
            ncol=3,
            frameon=False,
            fontsize=12,
        )
        fig.text(
            0.06,
            0.008,
            "百分位越高表示录取竞争越强，颜色越深；斜线=仅 1–2 所院校。灰色=该省该年没有可计算的临床专业池百分位，"
            "不表示 310 个省年框架缺少专业记录。右图以各省首个可用年份为 0，因此基线年份并不相同。\n"
            "2026 年：山东、辽宁、河北、浙江、重庆、贵州使用省级官方专业表；其余 25 个省级单位使用公开归档专业数据。",
            ha="left",
            va="bottom",
            fontsize=12,
            color=NOTE_COLOR,
            linespacing=1.45,
        )
        fig.subplots_adjust(left=0.095, right=0.94, top=0.89, bottom=0.16)
        png_path = FIGURES / f"fig_heatmap_{track}.png"
        svg_path = FIGURES / f"fig_heatmap_{track}.svg"
        fig.savefig(png_path, dpi=300, facecolor="white")
        fig.savefig(svg_path, facecolor="white")
        plt.close(fig)


def contiguous_segments(years: np.ndarray, values: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
    segments: list[tuple[np.ndarray, np.ndarray]] = []
    start = 0
    for index in range(1, len(years) + 1):
        if index == len(years) or years[index] - years[index - 1] > 1:
            segment_years = years[start:index]
            segment_values = values[start:index]
            if segment_years.size:
                segments.append((segment_years, segment_values))
            start = index
    return segments


def pchip_slopes(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    n = len(x)
    if n <= 2:
        return np.zeros(n, dtype=float)
    h = np.diff(x)
    delta = np.diff(y) / h
    slopes = np.zeros(n, dtype=float)
    for index in range(1, n - 1):
        if delta[index - 1] * delta[index] <= 0:
            slopes[index] = 0.0
            continue
        w1 = 2.0 * h[index] + h[index - 1]
        w2 = h[index] + 2.0 * h[index - 1]
        slopes[index] = (w1 + w2) / (
            w1 / delta[index - 1] + w2 / delta[index]
        )
    slopes[0] = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (
        h[0] + h[1]
    )
    slopes[-1] = (
        (2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]
    ) / (h[-1] + h[-2])
    if slopes[0] * delta[0] <= 0:
        slopes[0] = 0.0
    elif abs(slopes[0]) > 3.0 * abs(delta[0]):
        slopes[0] = 3.0 * delta[0]
    if slopes[-1] * delta[-1] <= 0:
        slopes[-1] = 0.0
    elif abs(slopes[-1]) > 3.0 * abs(delta[-1]):
        slopes[-1] = 3.0 * delta[-1]
    return slopes


def smooth_segment(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < 2:
        return x, y
    slopes = pchip_slopes(x, y)
    dense_x = []
    dense_y = []
    for index in range(len(x) - 1):
        interval = np.linspace(x[index], x[index + 1], 24, endpoint=True)
        h = x[index + 1] - x[index]
        t = (interval - x[index]) / h
        h00 = 2 * t**3 - 3 * t**2 + 1
        h10 = t**3 - 2 * t**2 + t
        h01 = -2 * t**3 + 3 * t**2
        h11 = t**3 - t**2
        values = (
            h00 * y[index]
            + h10 * h * slopes[index]
            + h01 * y[index + 1]
            + h11 * h * slopes[index + 1]
        )
        if index:
            dense_x.extend(interval[1:])
            dense_y.extend(values[1:])
        else:
            dense_x.extend(interval)
            dense_y.extend(values)
    return np.asarray(dense_x), np.asarray(dense_y)


def draw_smooth_series(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    color: str,
    alpha: float,
    linewidth: float,
    label: str | None = None,
) -> None:
    for segment_x, segment_y in contiguous_segments(x, y):
        if len(segment_x) >= 2:
            smooth_x, smooth_y = smooth_segment(segment_x, segment_y)
            ax.plot(
                smooth_x,
                smooth_y,
                color=color,
                alpha=alpha,
                linewidth=linewidth,
                label=label,
            )
        else:
            ax.scatter(
                segment_x,
                segment_y,
                color=color,
                alpha=alpha,
                s=14,
                label=label,
            )


def draw_province_curves(province_layer: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(14.2, 16.2), sharex=True)
    panels = ["all_clinical", "five_year", "eight_year"]
    for ax, track in zip(axes, panels):
        subset = province_layer[
            (province_layer["track"] == track)
            & (province_layer["metric"] == "admission_percentile")
            & (province_layer["meets_min_schools"])
        ]
        for province in PROVINCE_ORDER:
            one_province = subset[subset["province"] == province].sort_values("year")
            if one_province.empty:
                continue
            x = one_province["year"].to_numpy(dtype=int)
            y = one_province["value"].to_numpy(dtype=float)
            draw_smooth_series(
                ax,
                x,
                y,
                DEEP_BLUE,
                alpha=0.36,
                linewidth=2.0,
            )
            ax.scatter(
                x,
                y,
                s=32,
                color=DEEP_BLUE,
                alpha=0.90,
                edgecolor="white",
                linewidth=0.45,
                zorder=3,
            )
        if track == "eight_year":
            ax.set_ylim(90, 100)
        else:
            finite_values = subset["value"].dropna()
            lower = math.floor(float(finite_values.min()) / 5.0) * 5.0
            upper = math.ceil(float(finite_values.max()) / 5.0) * 5.0
            ax.set_ylim(max(0.0, lower - 2.0), min(100.0, upper + 2.0))
        ax.set_ylabel("专业池百分位（越高=竞争越强）")
        ax.set_title(
            f"{TRACKS[track]['label']}：各省逐年轨迹",
            loc="left",
            fontsize=17,
        )
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlim(2016.7, 2026.3)
    axes[-1].set_xticks(YEARS)
    axes[-1].set_xlabel("年份")
    fig.suptitle(
        "临床医学各省录取位置：原始年度点与平滑连接",
        x=0.055,
        y=0.992,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.010,
        "专业池百分位越高表示录取竞争越强。深蓝线连接相邻实测年份，不跨越缺失年份；每省每年至少 3 所院校才进入主曲线。",
        ha="left",
        fontsize=11,
        color=NOTE_COLOR,
    )
    fig.subplots_adjust(left=0.085, right=0.98, top=0.952, bottom=0.06, hspace=0.27)
    fig.savefig(FIGURES / "fig_province_curves_clinical.png", dpi=300)
    fig.savefig(FIGURES / "fig_province_curves_clinical.svg")
    plt.close(fig)


def draw_average_curves(curve_summary: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 7.0), sharex=False)
    track_order = ["all_clinical", "five_year", "eight_year"]
    for ax, track in zip(axes, track_order):
        subset = curve_summary[
            (curve_summary["track"] == track)
            & (curve_summary["metric"] == "admission_percentile")
        ].sort_values("year")
        x = subset["year"].to_numpy(dtype=int)
        mean = subset["mean"].to_numpy(dtype=float)
        low = subset["ci_low"].to_numpy(dtype=float)
        high = subset["ci_high"].to_numpy(dtype=float)
        ax.fill_between(x, low, high, color=DEEP_BLUE, alpha=0.22, linewidth=0)
        smooth_x, smooth_y = smooth_segment(x, mean)
        ax.plot(smooth_x, smooth_y, color=DEEP_BLUE, linewidth=3.4)
        ax.scatter(
            x,
            mean,
            color=DEEP_BLUE,
            edgecolor="white",
            linewidth=1.2,
            s=72,
            zorder=4,
        )
        ax.set_title(TRACKS[track]["short_label"], loc="left", fontsize=17)
        if track == "eight_year":
            ax.set_ylim(90, 100)
        else:
            ax.set_ylim(50, 80)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(YEARS)
        ax.set_xticklabels(
            [
                f"{year}\nn={int(n)}"
                for year, n in zip(x, subset["n_provinces"])
            ],
            fontsize=11,
        )
        ax.tick_params(axis="x", labelsize=11)
    for ax in axes:
        ax.set_xlabel("年份")
    axes[0].set_ylabel("专业池百分位（越高=竞争越强）")
    fig.suptitle(
        "省级单位的中位数均值图",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.025,
        "专业池百分位越高表示录取竞争越强。点和线为每年可用省份的省级中位数均值，年份下数字为纳入省份数；阴影带为按省份重采样的 95% 置信区间。",
        ha="left",
        fontsize=11,
        color=NOTE_COLOR,
    )
    fig.subplots_adjust(left=0.06, right=0.985, top=0.86, bottom=0.22, wspace=0.24)
    fig.savefig(FIGURES / "fig_average_curves.png", dpi=300)
    fig.savefig(FIGURES / "fig_average_curves.svg")
    plt.close(fig)


def draw_recent_balanced_change(balanced_recent: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(17.5, 8.2), sharex=False, sharey=False)
    rng = np.random.default_rng(RANDOM_SEED)

    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = balanced_recent[
            balanced_recent["track"].eq(track)
            & balanced_recent["comparison_eligible"]
        ].copy()
        means = {
            "all": subset["all_change"].mean(),
            "balanced": subset["balanced_change"].mean(),
        }
        for row in subset.itertuples():
            ax.plot(
                [0, 1],
                [row.balanced_change, row.all_change],
                color="#9ca3af",
                alpha=0.20,
                linewidth=0.9,
                zorder=1,
            )
        jitter_all = rng.uniform(-0.055, 0.055, len(subset))
        jitter_balanced = rng.uniform(-0.055, 0.055, len(subset))
        ax.scatter(
            jitter_balanced,
            subset["balanced_change"],
            color=DEEP_BLUE,
            s=24,
            alpha=0.70,
            edgecolor="white",
            linewidth=0.4,
            zorder=2,
        )
        ax.scatter(
            1 + jitter_all,
            subset["all_change"],
            color=LIGHT_BLUE,
            s=24,
            alpha=0.70,
            edgecolor="white",
            linewidth=0.4,
            zorder=2,
        )
        ax.scatter(
            [0, 1],
            [means["balanced"], means["all"]],
            color=[DEEP_BLUE, LIGHT_BLUE],
            s=120,
            marker="D",
            edgecolor="white",
            linewidth=1.2,
            zorder=4,
        )
        ax.annotate(
            f"{means['balanced']:+.1f}",
            (0, means["balanced"]),
            xytext=(-10, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=13,
            color=DEEP_BLUE,
        )
        ax.annotate(
            f"{means['all']:+.1f}",
            (1, means["all"]),
            xytext=(10, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=13,
            color=DEEP_BLUE,
        )
        ax.axhline(0, color="#374151", linewidth=0.9)
        panel_values = pd.concat(
            [subset["all_change"], subset["balanced_change"]],
            ignore_index=True,
        ).dropna()
        lower = min(0.0, float(panel_values.min()))
        upper = max(0.0, float(panel_values.max()))
        if track == "eight_year":
            panel_span = max(upper - lower, 0.4)
            panel_ylim = (lower - panel_span * 0.25, upper + panel_span * 0.25)
        else:
            panel_span = max(upper - lower, 1.0)
            panel_ylim = (lower - panel_span * 0.10, upper + panel_span * 0.12)
        ax.set_ylim(*panel_ylim)
        ax.set_xlim(-0.35, 1.35)
        ax.set_xticks(
            [0, 1],
            [
                "同校平衡样本\n两年共同院校",
                "全部可用院校\n每年校数可变",
            ],
            fontsize=12,
        )
        ax.set_xlabel("两种口径都计算 2025→2026 变化", fontsize=12.5)
        ax.set_title(
            f"{TRACKS[track]['short_label']}（{len(subset)}省）",
            loc="left",
            fontsize=18,
        )
        ax.set_ylabel("2025→2026 变化（百分点）")
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].legend(
        handles=[
            Line2D(
                [0],
                [0],
                color=DEEP_BLUE,
                marker="D",
                linewidth=2.2,
                label="同校平衡样本（两年共同院校）",
            ),
            Line2D(
                [0],
                [0],
                color=LIGHT_BLUE,
                marker="D",
                linewidth=2.2,
                label="全部可用院校（每年校数可变）",
            ),
        ],
        loc="lower left",
        frameon=False,
        fontsize=12,
    )
    fig.suptitle(
        "同一省份的 2025→2026 变化：同校样本与全部院校",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.028,
        "每条浅灰线连接同一省份在两种口径下的 2025→2026 变化值。线向右下倾斜，通常表示改用全部院校后跌幅变大；横向表示两种口径，并非时间从 2025 走到 2026。\n"
        "左列只保留同一省内两年都出现的院校，两年使用同一批学校。右列使用该省当年全部可用院校，两年校数及构成可以变化。\n"
        "全部临床和五年制各纳入 30 省；西藏因两年共同院校不足 3 所而不形成可比样本。八年制仅纳入 7 省：河北、山东、辽宁、重庆、贵州、吉林、内蒙古。\n"
        "三个面板使用各自纵轴，刻度数字给出实际量级，不能按点线高度跨面板直接比较。八年制均值约 -0.2 个百分点，纵轴范围明显更窄。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.31, wspace=0.22)
    fig.savefig(FIGURES / "fig_balanced_change_2025_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_balanced_change_2025_2026.svg")
    plt.close(fig)


def draw_long_balanced_panel(balanced_long: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(17.5, 8.4), sharex=True)
    coverage_info = {}
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = balanced_long[balanced_long["track"].eq(track)].copy()
        included = set(subset["province"])
        province_count = len(included)
        missing = [province for province in PROVINCE_ORDER if province not in included]
        coverage_info[track] = {"included": included, "missing": missing}
        all_curve = (
            subset.groupby("year")["all_value"].mean().reindex(LONG_BALANCED_YEARS)
        )
        balanced_curve = (
            subset.groupby("year")["balanced_value"]
            .mean()
            .reindex(LONG_BALANCED_YEARS)
        )
        x = np.asarray(LONG_BALANCED_YEARS)
        all_smooth_x, all_smooth_y = smooth_segment(
            x, all_curve.to_numpy(dtype=float)
        )
        balanced_smooth_x, balanced_smooth_y = smooth_segment(
            x, balanced_curve.to_numpy(dtype=float)
        )
        ax.plot(
            all_smooth_x,
            all_smooth_y,
            color=LIGHT_BLUE,
            linewidth=2.6,
            label="全部可用院校（每年校数可变）",
        )
        ax.scatter(
            x,
            all_curve,
            color=LIGHT_BLUE,
            edgecolor="white",
            linewidth=0.9,
            s=58,
            zorder=3,
        )
        ax.plot(
            balanced_smooth_x,
            balanced_smooth_y,
            color=DEEP_BLUE,
            linewidth=3.4,
            label="同校平衡样本（六年固定同校）",
        )
        ax.scatter(
            x,
            balanced_curve,
            color=DEEP_BLUE,
            edgecolor="white",
            linewidth=1.0,
            s=68,
            zorder=4,
        )
        if track == "eight_year":
            ax.set_ylim(90, 100)
        else:
            ax.set_ylim(50, 80)
        ax.set_title(
            f"{TRACKS[track]['short_label']}（纳入 {province_count}/31 省）",
            loc="left",
            fontsize=18,
        )
        ax.annotate(
            f"{all_curve.iloc[-1]:.1f}",
            (x[-1], all_curve.iloc[-1]),
            xytext=(6, -13),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=12,
            color=LIGHT_BLUE,
        )
        ax.annotate(
            f"{balanced_curve.iloc[-1]:.1f}",
            (x[-1], balanced_curve.iloc[-1]),
            xytext=(6, 12),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=12,
            color=DEEP_BLUE,
        )
        ax.set_xlim(2020.8, 2026.45)
        ax.set_xticks(LONG_BALANCED_YEARS)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("专业池百分位（越高=竞争越强）")
    axes[0].legend(frameon=False, fontsize=12, loc="upper left")
    for ax in axes:
        ax.set_xlabel("年份")
    fig.suptitle(
        "2021–2026 同省固定同校平衡样本",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.025,
        "浅蓝线：在纳入省份内使用每年全部可用院校，校数可变。深蓝线：只保留 2021–2026 六年连续出现、且每年每省至少 3 所共同院校的同一批学校，院校构成固定。\n"
        f"26/21/4 是固定同校后的交集覆盖，不是 31 省数据总覆盖。全部临床未纳入：{'、'.join(coverage_info['all_clinical']['missing'])}。\n"
        "五年制在全部临床排除的 5 省之外，又多排除上海、天津、山西、海南、甘肃；这 5 省仍作全院校曲线，但不足以形成六年固定同校样本。\n"
        f"八年制仅纳入：{'、'.join(province for province in PROVINCE_ORDER if province in coverage_info['eight_year']['included'])}。3 所共同院校是防止单校波动代表全省的最低门槛。",
        ha="left",
        fontsize=12,
        color=NOTE_COLOR,
        linespacing=1.4,
    )
    fig.subplots_adjust(left=0.06, right=0.98, top=0.86, bottom=0.31, wspace=0.22)
    fig.savefig(FIGURES / "fig_balanced_trend_2021_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_balanced_trend_2021_2026.svg")
    plt.close(fig)


def draw_track_premium(
    premium_province: pd.DataFrame, premium_school: pd.DataFrame
) -> None:
    province_summary = (
        premium_province.groupby("year")["track_gap"]
        .agg(
            median="median",
            q25=lambda values: values.quantile(0.25),
            q75=lambda values: values.quantile(0.75),
            n="size",
        )
        .reindex(YEARS)
    )
    school_summary = (
        premium_school.groupby("year")["track_gap"]
        .agg(
            median="median",
            q25=lambda values: values.quantile(0.25),
            q75=lambda values: values.quantile(0.75),
            n="size",
        )
        .reindex(YEARS)
    )
    province_ylim = (
        math.floor(float(province_summary["q25"].min()) / 5.0) * 5.0 - 2.0,
        math.ceil(float(province_summary["q75"].max()) / 5.0) * 5.0 + 2.0,
    )
    school_ylim = (
        min(-0.5, float(school_summary["q25"].min()) - 0.5),
        max(4.0, float(school_summary["q75"].max()) + 0.8),
    )

    fig, axes = plt.subplots(1, 2, figsize=(13.6, 7.6))
    for ax, summary, color, panel_title, count_unit, ylim in [
        (
            axes[0],
            province_summary,
            MUTED_BROWN,
            "同省配对（含院校构成）",
            "省",
            province_ylim,
        ),
        (
            axes[1],
            school_summary,
            DEEP_BLUE,
            "同校配对（控制院校）",
            "学校—省",
            school_ylim,
        ),
    ]:
        x = summary.index.to_numpy(dtype=int)
        ax.fill_between(
            x,
            summary["q25"],
            summary["q75"],
            color=color,
            alpha=0.18,
            linewidth=0,
        )
        ax.plot(
            x,
            summary["median"],
            color=color,
            linewidth=3.2,
            marker="o",
            markersize=8,
            markeredgecolor="white",
            markeredgewidth=1.1,
        )
        ax.axhline(0, color="#374151", linewidth=1.0, zorder=1)
        ax.set_title(panel_title, loc="left", fontsize=18)
        ax.set_xticks(
            YEARS,
            [
                f"{year}\nn={int(summary.loc[year, 'n'])}"
                if pd.notna(summary.loc[year, "n"])
                else f"{year}\nn=0"
                for year in YEARS
            ],
            fontsize=11.5,
        )
        ax.set_xlabel(f"年份（n={count_unit}）")
        ax.set_ylim(*ylim)
        last = summary.loc[2026]
        ax.text(
            0.03,
            0.95,
            f"2026 中位 {last['median']:.1f}\n"
            f"IQR {last['q25']:.1f}–{last['q75']:.1f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=12,
            color=NOTE_COLOR,
        )
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[0].set_ylabel("八年制 − 五年制（百分点）")
    axes[1].set_ylabel("八年制 − 五年制（百分点）")

    fig.suptitle(
        "五年制与八年制位次差：同省配对与同校配对",
        x=0.05,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.05,
        0.03,
        "差值 = 八年制百分位 − 五年制百分位，0 线表示两类学制没有差异。同省差包含院校层级构成；同校差只比较同一省、同一年、同一学校内部的两类学制。\n"
        "两图纵轴范围不同：左图约为 15–40，右图约为 0–5，保留的刻度数字用于说明量级，不能按线条高度直接比较。\n"
        "2026 年同省差中位为 34.2，同校差中位为 1.6。同校差约 1–2 个百分点表示同一所学校的八年制录取位置仍高于五年制，并非 0。\n"
        "同省差远大于同校差，主要反映八年制集中在更高层级院校。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(left=0.075, right=0.98, top=0.85, bottom=0.31, wspace=0.24)
    fig.savefig(FIGURES / "fig_track_premium.png", dpi=300)
    fig.savefig(FIGURES / "fig_track_premium.svg")
    plt.close(fig)


def draw_school_change_distribution(
    school_change_pairs: pd.DataFrame,
) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(16.5, 7.8), sharex=False, sharey=False
    )
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = school_change_pairs[
            school_change_pairs["track"].eq(track)
        ].copy()
        values = subset["change"].to_numpy(dtype=float)
        violin = ax.violinplot(
            [values],
            positions=[0],
            widths=0.72,
            showmeans=False,
            showmedians=False,
            showextrema=False,
        )
        for body in violin["bodies"]:
            body.set_facecolor(LIGHT_BLUE)
            body.set_edgecolor(DEEP_BLUE)
            body.set_alpha(0.48)
            body.set_linewidth(1.6)
        median_value = float(np.median(values))
        ax.hlines(
            median_value,
            -0.24,
            0.24,
            color=DEEP_BLUE,
            linewidth=3.0,
            zorder=4,
        )
        violin_y = violin["bodies"][0].get_paths()[0].vertices[:, 1]
        lower = float(np.min(violin_y))
        upper = float(np.max(violin_y))
        span = max(upper - lower, 0.5)
        ax.set_ylim(lower - span * 0.04, upper + span * 0.04)
        ax.axhline(0, color="#374151", linewidth=1.2)
        ax.set_xlim(-0.65, 0.65)
        ax.set_xticks([0], ["同校变化"])
        ax.set_ylabel("百分位变化（2025→2026）")
        ax.set_title(
            f"{TRACKS[track]['short_label']}（{len(subset)} 个配对）",
            loc="left",
            fontsize=18,
        )
        ax.text(
            0.03,
            0.96,
            f"中位 {median_value:+.1f}\n"
            f"下降占 {(values < 0).mean() * 100:.0f}%",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=13,
            color=NOTE_COLOR,
        )
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(
        "同一批院校内部的 2025→2026 百分位变化",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.03,
        "每个面板包含一个纯小提琴分布，横轴没有分组；深蓝横线为学校—省配对变化的中位数，黑线为零变化。\n"
        "小提琴的宽度表示同校变化在该数值附近的密度。纵轴覆盖完整小提琴包络，上下各留少量空白。\n"
        "同校配对只纳入该学制、该省2025和2026都可计算专业池百分位的同一所学校。该图描述校内变化分布，不用于推断因果。",
        ha="left",
        fontsize=13,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(
        left=0.06, right=0.98, top=0.86, bottom=0.27, wspace=0.24
    )
    fig.savefig(FIGURES / "fig_school_change_distribution_2025_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_school_change_distribution_2025_2026.svg")
    plt.close(fig)


def draw_school_count_change(school_count_change: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(18.0, 10.2), sharex=False, sharey=False
    )
    colors = {"A": DEEP_BLUE, "B": MUTED_BROWN}
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = (
            school_count_change[school_count_change["track"].eq(track)]
            .sort_values("school_count_change")
            .reset_index(drop=True)
        )
        y = np.arange(len(subset))
        ax.hlines(
            y,
            subset["n_schools_all_2025"],
            subset["n_schools_all_2026"],
            color="#9ca3af",
            linewidth=1.5,
            zorder=1,
        )
        ax.scatter(
            subset["n_schools_all_2025"],
            y,
            color=LIGHT_BLUE,
            s=58,
            edgecolor="white",
            linewidth=0.7,
            zorder=3,
            label="2025 可计算院校",
        )
        for group in ["A", "B"]:
            selected = subset["source_group_2026"].eq(group)
            if selected.any():
                ax.scatter(
                    subset.loc[selected, "n_schools_all_2026"],
                    y[selected.to_numpy()],
                    color=colors[group],
                    marker="D",
                    s=52,
                    edgecolor="white",
                    linewidth=0.7,
                    zorder=4,
                    label=(
                        "2026 官方专业表"
                        if group == "A"
                        else "2026 公开归档"
                    ),
                )
        ax.set_yticks(y, subset["province"], fontsize=11.5)
        ax.set_xlabel("可计算专业池百分位的院校数")
        median_delta = float(subset["school_count_change"].median())
        ax.set_title(
            f"{TRACKS[track]['short_label']}（中位 {median_delta:+.1f} 所）",
            loc="left",
            fontsize=18,
        )
        max_count = max(
            float(subset["n_schools_all_2025"].max()),
            float(subset["n_schools_all_2026"].max()),
        )
        ax.set_xlim(0, max_count * 1.12)
        ax.grid(axis="x", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(
        handles,
        legend_labels,
        loc="lower left",
        bbox_to_anchor=(0.055, 0.075),
        ncol=3,
        frameon=False,
        fontsize=12,
    )
    fig.suptitle(
        "2025→2026 可计算院校数量变化",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.018,
        "每行连接同一省份2025与2026的有专业池百分位院校数。2026公开归档层的院校覆盖明显窄于2025聚合层，因此院校数下降首先是口径和覆盖变化。\n"
        "这里统计的是“能进入专业池百分位计算的院校”，学校实际停招、撤销或未公开专业级记录都会造成下降，单凭本图不能区分这些原因。\n"
        "颜色标出2026来源层级。院校数变化是全部院校口径敏感性的重要来源，不能把全部院校跌幅直接写成所有学校同步下跌。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(
        left=0.085, right=0.985, top=0.89, bottom=0.18, wspace=0.34
    )
    fig.savefig(FIGURES / "fig_school_count_change_2025_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_school_count_change_2025_2026.svg")
    plt.close(fig)


def draw_leave_one_out(lovo: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(17.5, 10.2), sharex=False, sharey=False
    )
    colors = {"A": DEEP_BLUE, "B": MUTED_BROWN}
    subset_all = lovo[lovo["outcome"].eq("all_change")].copy()
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = (
            subset_all[subset_all["track"].eq(track)]
            .sort_values("lovo_mean")
            .reset_index(drop=True)
        )
        y = np.arange(len(subset))
        full_mean = float(subset["full_mean"].iloc[0])
        low = float(subset["lovo_mean"].min())
        high = float(subset["lovo_mean"].max())
        ax.axvspan(low, high, color=LIGHT_BLUE, alpha=0.14, linewidth=0)
        ax.axvline(
            full_mean,
            color="#374151",
            linewidth=1.5,
            linestyle="--",
            label="全样本均值",
        )
        for group in ["A", "B"]:
            selected = subset["source_group_2026"].eq(group)
            if selected.any():
                ax.scatter(
                    subset.loc[selected, "lovo_mean"],
                    y[selected.to_numpy()],
                    color=colors[group],
                    s=55,
                    edgecolor="white",
                    linewidth=0.7,
                    zorder=3,
                )
        ax.set_yticks(y, subset["excluded_province"], fontsize=11.5)
        ax.set_xlabel("排除该省后的剩余省份均值（百分点）")
        ax.set_title(
            f"{TRACKS[track]['short_label']}（n={len(subset)}）",
            loc="left",
            fontsize=18,
        )
        pad = max((high - low) * 0.25, 0.15)
        ax.set_xlim(low - pad, high + pad)
        ax.grid(axis="x", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.text(
            0.03,
            0.97,
            f"全样本 {full_mean:+.2f}\n"
            f"留一法范围 {low:+.2f}～{high:+.2f}",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=12,
            color=NOTE_COLOR,
        )
    axes[0].legend(frameon=False, fontsize=12, loc="lower left")
    fig.suptitle(
        "2025→2026 均值稳健性：逐省留一法",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.02,
        "每一行表示从当前样本中排除该省后，重新计算其余省份的2025→2026全部院校均值；虚线为未排除时的全样本均值。\n"
        "若留一法范围仍停留在同一方向且跨度很小，说明均值不由单个省份决定。该检验描述省级均值的样本敏感性，不替代完整的层级模型。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(
        left=0.08, right=0.985, top=0.89, bottom=0.15, wspace=0.34
    )
    fig.savefig(FIGURES / "fig_lopo_robustness_2025_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_lopo_robustness_2025_2026.svg")
    plt.close(fig)


def draw_school_tier_gradient(tier_change: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(17.5, 8.2), sharex=True, sharey=False
    )
    rng = np.random.default_rng(RANDOM_SEED + 23)
    tier_labels = ["低位", "中位", "高位"]
    tier_colors = [LIGHT_BLUE, MUTED_BLUE, DEEP_BLUE]
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = tier_change[tier_change["track"].eq(track)].copy()
        median_points = []
        for tier_index, tier_label in enumerate(tier_labels):
            one = subset[subset["tier"].eq(tier_label)]
            values = one["median_change"].to_numpy(dtype=float)
            jitter = rng.uniform(-0.13, 0.13, len(values))
            ax.scatter(
                tier_index + jitter,
                values,
                color=tier_colors[tier_index],
                s=42,
                alpha=0.72,
                edgecolor="white",
                linewidth=0.6,
                zorder=2,
            )
            median_points.append(
                float(np.median(values)) if len(values) else math.nan
            )
        ax.plot(
            range(3),
            median_points,
            color=DEEP_BLUE,
            linewidth=2.4,
            marker="D",
            markersize=9,
            markeredgecolor="white",
            markeredgewidth=1.0,
            zorder=4,
        )
        ax.axhline(0, color="#374151", linewidth=1.0)
        ax.set_xticks(
            range(3),
            [
                f"{label}\n"
                f"{subset.loc[subset['tier'].eq(label), 'province'].nunique()}省"
                for label in tier_labels
            ],
            fontsize=12.5,
        )
        all_values = subset["median_change"].to_numpy(dtype=float)
        q05, q95 = np.quantile(all_values, [0.05, 0.95])
        span = max(float(q95 - q05), 0.5)
        ax.set_ylim(float(q05 - span * 0.18), float(q95 + span * 0.18))
        ax.set_ylabel("同一批院校变化中位数（百分点）")
        ax.set_title(
            f"{TRACKS[track]['short_label']}（{len(subset)} 个省级层级）",
            loc="left",
            fontsize=18,
        )
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle("同校变化的院校层级梯度（2025→2026）", x=0.055, y=0.975,
                 ha="left", fontsize=22, fontweight="bold")
    fig.text(
        0.055,
        0.03,
        "在每个省内，只使用2025和2026都出现的同一批院校，按2025年校内专业池百分位等分为低位、中位、高位三层；每省至少需要6所共同院校。\n"
        "散点是各“省份×层级”的变化中位数，粗线连接三层跨省中位数。层级只表示该省当年的相对录取位置，不代表学校官方排名或办学质量。\n"
        "该图用于观察不同层级院校是否同步变化，不把层级差异解释为学校属性或政策效应。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(
        left=0.06, right=0.98, top=0.86, bottom=0.28, wspace=0.24
    )
    fig.savefig(FIGURES / "fig_school_tier_gradient_2025_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_school_tier_gradient_2025_2026.svg")
    plt.close(fig)


def draw_cumulative_change(cumulative: pd.DataFrame) -> None:
    fig, axes = plt.subplots(
        1, 3, figsize=(17.5, 8.2), sharex=True, sharey=False
    )
    for ax, track in zip(axes, CLINICAL_TRACKS):
        subset = cumulative[cumulative["track"].eq(track)].copy()
        provinces = sorted(subset["province"].unique())
        for province in provinces:
            one = subset[subset["province"].eq(province)].sort_values("year")
            ax.plot(
                one["year"],
                one["cumulative_change"],
                color=LIGHT_BLUE,
                linewidth=1.0,
                alpha=0.28,
                zorder=1,
            )
        summary = (
            subset.groupby("year")["cumulative_change"]
            .agg(
                median="median",
                q25=lambda values: values.quantile(0.25),
                q75=lambda values: values.quantile(0.75),
            )
            .reindex(LONG_BALANCED_YEARS)
        )
        ax.fill_between(
            LONG_BALANCED_YEARS,
            summary["q25"],
            summary["q75"],
            color=LIGHT_BLUE,
            alpha=0.28,
            linewidth=0,
            zorder=2,
        )
        ax.plot(
            LONG_BALANCED_YEARS,
            summary["median"],
            color=DEEP_BLUE,
            linewidth=3.2,
            marker="o",
            markersize=8,
            markeredgecolor="white",
            markeredgewidth=1.0,
            zorder=4,
        )
        ax.axhline(0, color="#374151", linewidth=1.0)
        ax.set_xticks(LONG_BALANCED_YEARS)
        ax.set_xlabel("年份")
        ax.set_ylabel("相对2021年的累计变化（百分点）")
        ax.set_title(
            f"{TRACKS[track]['short_label']}（{len(provinces)} 省）",
            loc="left",
            fontsize=18,
        )
        last_value = float(summary.loc[2026, "median"])
        ax.annotate(
            f"{last_value:+.1f}",
            (2026, last_value),
            xytext=(7, 8),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=12.5,
            color=DEEP_BLUE,
        )
        all_values = subset["cumulative_change"].to_numpy(dtype=float)
        q05, q95 = np.quantile(all_values, [0.05, 0.95])
        span = max(float(q95 - q05), 0.5)
        ax.set_ylim(float(q05 - span * 0.14), float(q95 + span * 0.14))
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    fig.suptitle(
        "固定同校样本的累计变化轨迹（2021=0）",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.03,
        "每条细线代表一个省，数值为该省固定同校样本相对2021年的累计变化；粗线为跨省中位数，阴影带为25%–75%分位区间。\n"
        "样本沿用2021–2026连续六年出现、每年每省至少3所共同院校的固定同校集合。八年制只有4省，不能外推为全国八年制趋势。\n"
        "基期统一为2021只用于比较变化形状；不同省份的绝对录取百分位水平仍不相同。",
        ha="left",
        fontsize=12.5,
        color=NOTE_COLOR,
        linespacing=1.45,
    )
    fig.subplots_adjust(
        left=0.06, right=0.98, top=0.86, bottom=0.28, wspace=0.24
    )
    fig.savefig(FIGURES / "fig_cumulative_change_2021_2026.png", dpi=300)
    fig.savefig(FIGURES / "fig_cumulative_change_2021_2026.svg")
    plt.close(fig)


def build_year_change_summary(province_layer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track in TRACKS:
        for metric in METRICS:
            subset = province_layer[
                (province_layer["track"] == track)
                & (province_layer["metric"] == metric)
                & (province_layer["meets_min_schools"])
            ]
            pivot = subset.pivot(index="province", columns="year", values="value")
            for year in range(2018, 2027):
                if year not in pivot.columns or year - 1 not in pivot.columns:
                    continue
                delta = (pivot[year] - pivot[year - 1]).dropna()
                rows.append(
                    {
                        "track": track,
                        "track_label": TRACKS[track]["label"],
                        "metric": metric,
                        "metric_label": METRICS[metric]["label"],
                        "year": year,
                        "n_provinces_paired": int(len(delta)),
                        "mean_change": float(delta.mean()) if len(delta) else math.nan,
                        "median_change": (
                            float(delta.median()) if len(delta) else math.nan
                        ),
                        "share_declining": (
                            float(delta.lt(0).mean()) if len(delta) else math.nan
                        ),
                        "share_drop_ge_5": (
                            float(delta.le(-5).mean()) if len(delta) else math.nan
                        ),
                        "share_drop_ge_10": (
                            float(delta.le(-10).mean()) if len(delta) else math.nan
                        ),
                    }
                )
    return pd.DataFrame(rows)


def build_slogan_tests(year_change: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track, target_year, statement in [
        ("all_clinical", 2025, "临床死于2025"),
        ("five_year", 2025, "五年制临床死于2025"),
    ]:
        subset = year_change[
            (year_change["track"] == track)
            & (year_change["metric"] == "admission_percentile")
        ].copy()
        chosen = subset[subset["year"] == target_year]
        if chosen.empty:
            continue
        row = chosen.iloc[0]
        most_negative = subset.sort_values("mean_change").iloc[0]
        most_widespread = subset.sort_values("share_declining", ascending=False).iloc[0]
        rows.append(
            {
                "statement": statement,
                "track": track,
                "target_year": target_year,
                "n_provinces_paired": int(row["n_provinces_paired"]),
                "mean_change": row["mean_change"],
                "median_change": row["median_change"],
                "share_declining": row["share_declining"],
                "share_drop_ge_5": row["share_drop_ge_5"],
                "share_drop_ge_10": row["share_drop_ge_10"],
                "largest_mean_drop_year": int(most_negative["year"]),
                "largest_mean_drop": most_negative["mean_change"],
                "most_widespread_drop_year": int(most_widespread["year"]),
                "most_widespread_drop_share": most_widespread["share_declining"],
            }
        )

    clinical_2025 = year_change[
        (year_change["track"] == "all_clinical")
        & (year_change["metric"] == "admission_percentile")
        & (year_change["year"] == 2025)
    ].iloc[0]
    clinical_2026 = year_change[
        (year_change["track"] == "all_clinical")
        & (year_change["metric"] == "admission_percentile")
        & (year_change["year"] == 2026)
    ].iloc[0]
    rows.append(
        {
            "statement": "临床降温在2025开始，2026构成更强年度断裂",
            "track": "all_clinical",
            "target_year": 2026,
            "n_provinces_paired": int(clinical_2026["n_provinces_paired"]),
            "mean_change": clinical_2026["mean_change"],
            "median_change": clinical_2026["median_change"],
            "share_declining": clinical_2026["share_declining"],
            "share_drop_ge_5": clinical_2026["share_drop_ge_5"],
            "share_drop_ge_10": clinical_2026["share_drop_ge_10"],
            "largest_mean_drop_year": 2026,
            "largest_mean_drop": clinical_2026["mean_change"],
            "most_widespread_drop_year": 2026,
            "most_widespread_drop_share": clinical_2026["share_declining"],
            "comparison_2025_mean_change": clinical_2025["mean_change"],
            "comparison_2025_share_declining": clinical_2025["share_declining"],
        }
    )
    return pd.DataFrame(rows)


def build_2026_source_sensitivity(province_layer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track in TRACKS:
        subset = province_layer[
            (province_layer["track"] == track)
            & (province_layer["metric"] == "admission_percentile")
            & (province_layer["meets_min_schools"])
        ]
        current = subset[subset["year"] == 2026].copy()
        previous = subset[subset["year"] == 2025][["province", "value"]].rename(
            columns={"value": "value_2025"}
        )
        current = current.merge(previous, on="province", how="left")
        current["change_2025_2026"] = current["value"] - current["value_2025"]
        for source_group_name in ["A", "B", "A+B"]:
            group = current[current["source_group"] == source_group_name]
            if group.empty:
                continue
            paired = group.dropna(subset=["change_2025_2026"])
            rows.append(
                {
                    "track": track,
                    "track_label": TRACKS[track]["label"],
                    "source_group_2026": source_group_name,
                    "n_provinces": len(group),
                    "mean_2026": group["value"].mean(),
                    "median_2026": group["value"].median(),
                    "n_paired_2025_2026": len(paired),
                    "mean_change_2025_2026": (
                        paired["change_2025_2026"].mean() if len(paired) else math.nan
                    ),
                    "median_change_2025_2026": (
                        paired["change_2025_2026"].median() if len(paired) else math.nan
                    ),
                    "share_declining_2025_2026": (
                        paired["change_2025_2026"].lt(0).mean()
                        if len(paired)
                        else math.nan
                    ),
                }
            )
        paired_all = current.dropna(subset=["change_2025_2026"])
        rows.append(
            {
                "track": track,
                "track_label": TRACKS[track]["label"],
                "source_group_2026": "ALL",
                "n_provinces": len(current),
                "mean_2026": current["value"].mean(),
                "median_2026": current["value"].median(),
                "n_paired_2025_2026": len(paired_all),
                "mean_change_2025_2026": paired_all["change_2025_2026"].mean(),
                "median_change_2025_2026": paired_all["change_2025_2026"].median(),
                "share_declining_2025_2026": paired_all["change_2025_2026"].lt(0).mean(),
            }
        )
    return pd.DataFrame(rows)


def draw_annual_change_figure(year_change: pd.DataFrame) -> None:
    panels = ["all_clinical", "five_year", "eight_year"]
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 7.0), sharex=True, sharey=True)
    all_changes = []
    for track in panels:
        subset = year_change[
            (year_change["track"] == track)
            & (year_change["metric"] == "admission_percentile")
        ]
        all_changes.extend(subset["mean_change"].dropna().tolist())
    common_lower = min(0.0, float(np.nanmin(all_changes)))
    common_upper = max(0.0, float(np.nanmax(all_changes)))
    common_span = max(common_upper - common_lower, 0.2)
    common_ylim = (
        common_lower - common_span * 0.12,
        common_upper + common_span * 0.18,
    )

    for ax, track in zip(axes, panels):
        subset = year_change[
            (year_change["track"] == track)
            & (year_change["metric"] == "admission_percentile")
        ].sort_values("year")
        years = subset["year"].to_numpy(dtype=int)
        changes = subset["mean_change"].to_numpy(dtype=float)
        share = subset["share_declining"].to_numpy(dtype=float) * 100
        colors = [MUTED_BLUE if value < 0 else WARM_SAND for value in changes]
        ax.bar(
            years,
            changes,
            color=colors,
            alpha=0.84,
            width=0.68,
            edgecolor="white",
            linewidth=0.6,
        )
        ax.axhline(0, color="#374151", linewidth=0.9)
        ax.set_title(TRACKS[track]["short_label"], loc="left", fontsize=16.5)
        ax.set_ylim(*common_ylim)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xticks(years)
        ax2 = ax.twinx()
        ax2.plot(
            years,
            share,
            color=DEEP_BLUE,
            marker="o",
            markersize=8,
            markeredgecolor="white",
            markeredgewidth=1.2,
            linewidth=3.0,
            alpha=0.88,
            label="下跌省份占比",
        )
        ax2.set_ylim(0, 100)
        if track == panels[0]:
            ax2.set_ylabel("下跌省份占比（%）", color=NOTE_COLOR)
        else:
            ax2.set_ylabel("")
            ax2.tick_params(axis="y", labelright=False)
            ax2.spines["right"].set_visible(False)
        ax2.tick_params(axis="y", colors="#4b5563")
        ax2.spines["top"].set_visible(False)
        ax2.spines["left"].set_visible(False)
    axes[0].set_ylabel("省级变化均值（百分点）")
    axes[0].legend(
        handles=[
            Line2D(
                [0],
                [0],
                color=DEEP_BLUE,
                marker="o",
                markersize=7,
                linewidth=2.6,
                label="下跌省份占比",
            )
        ],
        loc="upper left",
        frameon=False,
        fontsize=11,
    )
    for ax in axes:
        ax.set_xlabel("年份")
        ax.set_xticks(range(2018, 2027))
        ax.tick_params(axis="x", labelsize=11)
    fig.suptitle(
        "临床医学年度变化与同步性",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.025,
        "柱为相邻两年均有可用值的省份专业池百分位变化均值，深蓝线为当年下跌省份占比。三幅图共用左侧纵轴，便于比较变化幅度。",
        ha="left",
        fontsize=11,
        color=NOTE_COLOR,
    )
    fig.subplots_adjust(left=0.06, right=0.96, top=0.86, bottom=0.22, wspace=0.30)
    fig.savefig(FIGURES / "fig_annual_changes.png", dpi=300)
    fig.savefig(FIGURES / "fig_annual_changes.svg")
    plt.close(fig)


def draw_metric_robustness(curve_summary: pd.DataFrame) -> None:
    panels = ["all_clinical", "five_year", "eight_year"]
    fig, axes = plt.subplots(1, 3, figsize=(16.5, 7.0), sharex=True)
    for ax, track in zip(axes, panels):
        for metric, color, marker, label in [
            ("admission_percentile", DEEP_BLUE, "o", "专业池录取百分位"),
            ("candidate_percentile", MUTED_BROWN, "s", "考生分布百分位"),
        ]:
            subset = curve_summary[
                (curve_summary["track"] == track)
                & (curve_summary["metric"] == metric)
            ].sort_values("year")
            x = subset["year"].to_numpy(dtype=int)
            y = subset["mean"].to_numpy(dtype=float)
            smooth_x, smooth_y = smooth_segment(x, y)
            ax.plot(
                smooth_x,
                smooth_y,
                color=color,
                linewidth=3.2,
                label=label,
            )
            ax.scatter(
                x,
                y,
                color=color,
                marker=marker,
                s=62,
                edgecolor="white",
                linewidth=1.0,
            )
        ax.set_title(TRACKS[track]["short_label"], loc="left", fontsize=16.5)
        ax.set_xticks(YEARS)
        ax.tick_params(axis="x", labelsize=11)
        ax.grid(axis="y", color=GRID_COLOR, linewidth=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_ylabel("省级均值（越高=竞争越强）")
        if track == "eight_year":
            ax.set_ylim(90, 100)
        else:
            ax.set_ylim(50, 90)
    axes[0].legend(frameon=False, fontsize=11)
    fig.suptitle(
        "两种省内百分位指标的稳健性对照",
        x=0.055,
        y=0.975,
        ha="left",
        fontsize=22,
        fontweight="bold",
    )
    fig.text(
        0.055,
        0.025,
        "两种指标使用不同分母，不作为同一尺度拼接；这里只比较年度方向是否一致。百分位越高表示竞争越强。",
        ha="left",
        fontsize=11,
        color=NOTE_COLOR,
    )
    fig.subplots_adjust(left=0.06, right=0.985, top=0.86, bottom=0.22, wspace=0.24)
    fig.savefig(FIGURES / "fig_metric_robustness.png", dpi=300)
    fig.savefig(FIGURES / "fig_metric_robustness.svg")
    plt.close(fig)


def build_change_table(province_layer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track in TRACKS:
        subset = province_layer[
            (province_layer["track"] == track)
            & (province_layer["metric"] == "admission_percentile")
            & (province_layer["meets_min_schools"])
        ]
        for province in PROVINCE_ORDER:
            one = subset[subset["province"] == province].set_index("year")["value"]
            baseline = one.get(2017, math.nan)
            final = one.get(2026, math.nan)
            rows.append(
                {
                    "track": track,
                    "track_label": TRACKS[track]["label"],
                    "province": province,
                    "value_2017": baseline,
                    "value_2025": one.get(2025, math.nan),
                    "value_2026": final,
                    "change_2017_2025": one.get(2025, math.nan) - baseline,
                    "change_2017_2026": final - baseline,
                    "change_2025_2026": final - one.get(2025, math.nan),
                    "n_years": int(one.index.nunique()),
                    "complete_2017_2026": all(year in one.index for year in YEARS),
                }
            )
    return pd.DataFrame(rows)


def build_metric_comparison(province_layer: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for track in TRACKS:
        subset = province_layer[province_layer["track"] == track]
        pivot = subset.pivot_table(
            index=["province", "year"],
            columns="metric",
            values="value",
            aggfunc="first",
        ).reset_index()
        pair = pivot.dropna(subset=["admission_percentile", "candidate_percentile"])
        if len(pair) >= 3:
            professional_ranks = pair["admission_percentile"].rank(method="average")
            candidate_ranks = pair["candidate_percentile"].rank(method="average")
            correlation = float(
                np.corrcoef(professional_ranks, candidate_ranks)[0, 1]
            )
        else:
            correlation = math.nan
        rows.append(
            {
                "track": track,
                "track_label": TRACKS[track]["label"],
                "paired_cells": len(pair),
                "spearman_professional_vs_candidate": correlation,
            }
        )
    return pd.DataFrame(rows)


def write_methods() -> None:
    text = f"""# 趋势分析口径

## 主数据

- 使用 `output/clinical_panel_2017_2026_candidate_percentile.csv` 的 36,866 条临床医学专业级记录；其他专业记录不进入本分析。
- 2017–2025 年使用现有专业级扩展面板；2026 年将 6 个官方省级专业表和其余 25 个公开归档专业表放入同一省年分析。
- 2026 年保留“省级官方专业表”和“公开归档专业数据”来源标记用于溯源和来源敏感性分析，不把归档记录写成考试院原表。
- 港澳台不纳入本分析。

## 指标与院校等权

- 主指标为 `admission_percentile`：在同省、同年、同科类、同批次专业池中的最低分或最低位次百分位。数值越高，录取竞争位置越高。
- 稳健性指标为 `candidate_percentile`：同省同年考生分布中的位次百分位。
- 先计算同省、同年、同院校的专业中位数，再对院校取中位数，形成省级年度值。这样避免专业条目特别多的院校获得过高权重。
- 热图显示所有可计算的省年值；1–2 所院校的单元用斜线标出，避免把单校锚点当成全省代表。曲线默认要求每个省年至少 3 所院校。
- 热图中的灰色表示该省该年没有可计算的专业池百分位，不代表 310 个省年框架缺少专业记录。
- 水平热图颜色越深，录取竞争越强。变化热图蓝色表示相对升温，褐色表示相对降温；变化以各省首个可用年份为基线，因此基线年份并不相同。

## 临床学制

- “五年制”由 `explicit_five_year` 和没有长学制标记的普通本科临床记录组成。录取汇总没有独立、完整的培养年限字段，因此这是一个有明确边界的五年制识别口径。
- “八年制”只纳入专业名或备注明确标记为八年制的记录。
- “临床医学（全部）”包括全部本科临床记录。三个类别分别统计，不把八年制当作全体临床的代表。
- 八年制的可识别省年覆盖明显低于全部临床和五年制，灰色单元不能解释为该省没有八年制培养，只表示当前数据无法形成可计算的八年制专业池百分位。

## 曲线与区间

- 省级曲线用 PCHIP 单调三次插值连接相邻实测年份，只改善视觉连接，不产生新的观测值。
- 缺少年份不跨越插值。
- 均值曲线按年计算所有可用省份的省级中位数均值。
- 95% 区间通过按省份重采样 2,000 次计算，反映省份均值的抽样不确定性。各省可用数量不同，图中直接标注每年纳入的省份数。

## 同校平衡样本

- 2025→2026 平衡样本只保留两个年份都出现的同省同校记录；每个省至少保留 3 所共同院校才进入比较。
- “全部可用院校”指在该组已经限定的省份集合内，使用每年全部有目标专业记录的院校；院校数量和院校构成均可变化。“固定同校”指只使用同省两年或六年都出现的同一批院校，院校构成固定。
- 2025→2026 比较中，全部临床和五年制各纳入 30 省；西藏因两年共同院校不足 3 所而不进入平衡比较。八年制只有河北、山东、辽宁、重庆、贵州、吉林、内蒙古 7 省达到门槛。
- 2021–2026 长平衡样本要求院校在六个年份均出现，并且每个省每年至少有 3 所共同院校。
- 2021–2026 长平衡样本中，全部临床纳入 26 省，未纳入河北、江西、河南、云南、西藏；五年制纳入 21 省，除上述 5 省外，上海、天津、山西、海南、甘肃也未达到六年固定同校门槛。八年制只有内蒙古、吉林、山东、重庆 4 省达到门槛。
- 26/21/4 表示固定同校后的分析交集覆盖，不表示这 31 个省级单位的原始数据只覆盖 26、21 或 4 省。降低“每省至少 3 所共同院校”的门槛会扩大样本，但单校波动更容易代表全省，因此本文不在主分析中放宽。
- 同校结果用于判断总体均值对院校构成变化的敏感程度，不把全部院校与固定同校之间的差值解释为严格的因果分解。
- 2025→2026 第一张平衡图让三个面板使用各自纵轴，并保留坐标刻度。八年制均值约 -0.2 个百分点，纵轴范围明显窄于全部临床和五年制；读图时以刻度数字判断量级，不能按点线高度跨面板比较。

## 同校内部变化分布

- 每个“学校—省”配对是一个观测。分布图用纯小提琴展示密度，深蓝横线为中位数，黑线为零变化，不再混用箱线图或省级散点。
- 2025→2026 同校配对要求该学制、该省、该院校两个年份都有可计算的专业池百分位。分布图纵轴覆盖完整小提琴包络，极端值不会被裁掉。
- 逐校变化不是相互独立的随机样本，图中比例和分位数只作描述，正式不确定性同时参考省级留一法和固定同校结果。

## 可计算院校数

- 可计算院校数只统计能够进入专业池百分位计算的学校。2026年公开归档层覆盖面较窄，院校数变化首先用于诊断口径敏感性，不能直接写成学校停招、撤销或退出招生。

## 留一省稳健性

- 对每个临床类别，依次排除一个省份并重新计算剩余省份的2025→2026均值。留一法范围用于判断总体均值是否由个别省份主导。
- 留一法只反映省级均值的样本敏感性，不处理年份、院校和省份的多层抽样，也不替代正式分层模型。

## 院校层级梯度

- 在同省、同学制内，只保留2025和2026都出现的院校，并按2025年院校专业池百分位等分为低位、中位、高位三层；每省至少需要6所共同院校。
- 层级是省内相对录取位置，不是学校官方排名、办学质量或固定校档。省份×层级先取学校变化中位数，再跨省比较。

## 累计变化轨迹

- 固定同校累计变化以2021年为0，逐省计算2021–2026累计差值。粗线为跨省中位数，阴影带为25%–75%分位区间。
- 累计图沿用2021–2026六年固定同校样本，全部临床26省、五年制21省、八年制4省。八年制样本不能外推到全国。

## 学制位次差

- 学制位次差定义为同省同年八年制专业池百分位减五年制专业池百分位，正值表示八年制录取竞争位置更高。
- 同省配对要求该省同年两类学制都有至少 3 所院校。
- 同校配对要求同一省份、同一年、同一院校同时存在可计算的五年制和八年制记录。
- 同省差值包含院校构成差异，同校差值控制院校构成；两图并列展示，避免把同省差值单独解释为学制本身的溢价。
- 2026 年同省配对中位差为 34.2 个百分点（8 省），同校配对中位差为 1.6 个百分点（54 个学校—省配对）。同校差为正表示同一学校内八年制录取位置仍略高于五年制；1.6 个百分位不是零差异，也不能解释为学制本身的因果收益。

## 解释边界

- 结果描述报考与录取竞争位置，不能直接等同于就业质量、收入、岗位数量或行业生命周期。
- 2026 年公开归档省份与六个官方省级专业表省份共同进入主分析，同时单列来源敏感性分析。若两类来源、两种百分位指标和同校平衡样本指向一致，结论更可信。
- “临床医学死于2025”属于公共讨论中的形象表达。本报告只检验它能对应到哪一类可量化指标，不把录取变化扩展成就业或行业寿命判断。
"""
    (ROOT / "ANALYSIS_METHODS.md").write_text(text, encoding="utf-8")


def write_preliminary_findings(
    curve_summary: pd.DataFrame,
    change_table: pd.DataFrame,
    year_change: pd.DataFrame,
    slogan_tests: pd.DataFrame,
    source_sensitivity: pd.DataFrame,
    balanced_recent: pd.DataFrame,
    balanced_long: pd.DataFrame,
    premium_province: pd.DataFrame,
    premium_school: pd.DataFrame,
    school_change_pairs: pd.DataFrame,
    school_count_change: pd.DataFrame,
    lovo: pd.DataFrame,
    tier_change: pd.DataFrame,
    cumulative: pd.DataFrame,
) -> None:
    rows = []
    for track in TRACKS:
        one = curve_summary[
            (curve_summary["track"] == track)
            & (curve_summary["metric"] == "admission_percentile")
        ].set_index("year")
        values = ", ".join(
            f"{year}: {one.loc[year, 'mean']:.1f} (n={int(one.loc[year, 'n_provinces'])})"
            for year in YEARS
            if year in one.index and pd.notna(one.loc[year, "mean"])
        )
        rows.append(
            f"- **{TRACKS[track]['label']}** 的年度均值：{values}。"
        )

    top_changes = change_table.dropna(subset=["change_2017_2026"]).copy()
    rows.append("")
    rows.append("### 2017→2026 变化最大的省份")
    for track in CLINICAL_TRACKS:
        subset = (
            top_changes[top_changes["track"] == track]
            .sort_values("change_2017_2026")
            .head(5)
        )
        if subset.empty:
            rows.append(f"- **{TRACKS[track]['label']}**：没有可比较的十年连续省份。")
            continue
        values = "；".join(
            f"{row.province} {row.change_2017_2026:+.1f}"
            for row in subset.itertuples()
        )
        rows.append(f"- **{TRACKS[track]['label']}**：{values}。")

    rows.append("")
    rows.append("### 年度同步性")
    for track in CLINICAL_TRACKS:
        subset = year_change[
            (year_change["track"] == track)
            & (year_change["metric"] == "admission_percentile")
        ].sort_values("year")
        strongest = subset.sort_values("mean_change").iloc[0]
        widest = subset.sort_values("share_declining", ascending=False).iloc[0]
        rows.append(
            f"- **{TRACKS[track]['label']}**：最大年度均值跌幅出现在 "
            f"{int(strongest['year'])} 年（{strongest['mean_change']:+.1f} 个百分点）；"
            f"下跌省份占比最高的是 {int(widest['year'])} 年"
            f"（{widest['share_declining'] * 100:.1f}%）。"
        )

    rows.append("")
    rows.append("### “死亡年份”检验")
    for row in slogan_tests.itertuples():
        rows.append(
            f"- **{row.statement}**：目标年 {row.target_year} 的均值变化 "
            f"{row.mean_change:+.1f} 个百分点，"
            f"{row.share_declining * 100:.1f}% 的配对省份下跌，"
            f"{row.share_drop_ge_5 * 100:.1f}% 下跌至少 5 个百分点。"
        )

    rows.append("")
    rows.append("### 2026 来源敏感性")
    for track in CLINICAL_TRACKS:
        subset = source_sensitivity[
            (source_sensitivity["track"] == track)
            & (source_sensitivity["source_group_2026"].isin(["A", "B", "ALL"]))
        ]
        source_labels = {
            "A": "官方六省",
            "B": "公开归档25省",
            "ALL": "合并31省",
        }
        values = "；".join(
            f"{source_labels.get(row.source_group_2026, row.source_group_2026)}: "
            f"均值 {row.mean_2026:.1f}，"
            f"2025→2026 {row.mean_change_2025_2026:+.1f}"
            for row in subset.itertuples()
        )
        rows.append(f"- **{TRACKS[track]['label']}**：{values}。")

    rows.append("")
    rows.append("### 同校平衡样本")
    recent_included = {
        track: {
            row["province"]
            for row in balanced_recent.to_dict("records")
            if row["track"] == track and row["comparison_eligible"]
        }
        for track in CLINICAL_TRACKS
    }
    long_included = {
        track: set(
            balanced_long.loc[
                balanced_long["track"].eq(track), "province"
            ].unique()
        )
        for track in CLINICAL_TRACKS
    }
    recent_all_missing = [
        province
        for province in PROVINCE_ORDER
        if province not in recent_included["all_clinical"]
    ]
    recent_eight_included = [
        province
        for province in PROVINCE_ORDER
        if province in recent_included["eight_year"]
    ]
    long_all_missing = [
        province
        for province in PROVINCE_ORDER
        if province not in long_included["all_clinical"]
    ]
    long_five_extra_missing = [
        province
        for province in PROVINCE_ORDER
        if province not in long_included["five_year"]
        and province in long_included["all_clinical"]
    ]
    long_eight_included = [
        province
        for province in PROVINCE_ORDER
        if province in long_included["eight_year"]
    ]
    rows.append(
        "- **两线含义**：浅蓝线使用同一组省份内每年全部可用院校，"
        "院校数量与构成可变；深蓝线只使用固定年份内持续出现的同一批院校，"
        "用于控制院校构成变化。"
    )
    rows.append(
        f"- **2025→2026 样本**：全部临床和五年制各纳入 "
        f"{len(recent_included['all_clinical'])} 省；"
        f"{'、'.join(recent_all_missing)}未达到每省至少 3 所共同院校的门槛。"
        f"八年制仅纳入 {len(recent_eight_included)} 省："
        f"{'、'.join(recent_eight_included)}。"
    )
    rows.append(
        f"- **2021–2026 样本**：全部临床纳入 "
        f"{len(long_included['all_clinical'])} 省，未纳入"
        f"{'、'.join(long_all_missing)}；五年制纳入 "
        f"{len(long_included['five_year'])} 省，在全部临床基础上又未纳入"
        f"{'、'.join(long_five_extra_missing)}。"
        f"这些省份缺少连续六年、每年至少 3 所的共同院校。"
    )
    rows.append(
        f"- **八年制长期样本**：仅 {len(long_eight_included)} 省达到门槛，"
        f"即{'、'.join(long_eight_included)}。其百分位集中在 99 左右，"
        "图中使用较窄纵轴并保留刻度，便于看清小幅变化；跨面板比较仍需依据刻度数字。"
    )
    for track in CLINICAL_TRACKS:
        recent = balanced_recent[
            balanced_recent["track"].eq(track)
            & balanced_recent["comparison_eligible"]
        ]
        long = balanced_long[balanced_long["track"].eq(track)]
        all_2025 = long.loc[long["year"].eq(2025), "all_value"].mean()
        all_2026 = long.loc[long["year"].eq(2026), "all_value"].mean()
        balanced_2025 = long.loc[
            long["year"].eq(2025), "balanced_value"
        ].mean()
        balanced_2026 = long.loc[
            long["year"].eq(2026), "balanced_value"
        ].mean()
        rows.append(
            f"- **{TRACKS[track]['label']}**：2025→2026 同校样本覆盖 "
            f"{recent['province'].nunique()} 省。全部院校均值变化 "
            f"{recent['all_change'].mean():+.1f} 个百分点，同校变化 "
            f"{recent['balanced_change'].mean():+.1f} 个百分点。"
            f"2021–2026 固定同校样本覆盖 {long['province'].nunique()} 省；"
            f"同一子样本 2025→2026 的全部院校均值 "
            f"{all_2025:.1f}→{all_2026:.1f}，固定同校均值 "
            f"{balanced_2025:.1f}→{balanced_2026:.1f}。"
        )

    rows.append("")
    rows.append("### 五年制与八年制位次差")
    for year in [2025, 2026]:
        province_gap = premium_province[
            premium_province["year"].eq(year)
        ]["track_gap"]
        school_gap = premium_school[
            premium_school["year"].eq(year)
        ]["track_gap"]
        rows.append(
            f"- **{year} 年**：同省配对中位差 "
            f"{province_gap.median():.1f} 个百分点（{len(province_gap)} 省）；"
            f"同校配对中位差 {school_gap.median():.1f} 个百分点"
            f"（{len(school_gap)} 个学校—省配对）。"
        )

    rows.append("")
    rows.append("### 同校内部变化分布")
    for track in CLINICAL_TRACKS:
        subset = school_change_pairs[
            school_change_pairs["track"].eq(track)
        ]
        province_medians = subset.groupby("province")["change"].median()
        rows.append(
            f"- **{TRACKS[track]['label']}**：{subset['province'].nunique()} 省、"
            f"{len(subset)} 个学校—省配对。学校配对变化中位数 "
            f"{subset['change'].median():+.2f} 个百分点，"
            f"{subset['change'].lt(0).mean() * 100:.1f}% 的配对环境下降；"
            f"省级中位数的中位数为 {province_medians.median():+.2f}。"
        )

    rows.append("")
    rows.append("### 可计算院校数")
    for track in CLINICAL_TRACKS:
        counts = school_count_change[
            school_count_change["track"].eq(track)
        ]
        rows.append(
            f"- **{TRACKS[track]['label']}**：可计算院校数中位数 "
            f"{counts['n_schools_all_2025'].median():.1f}→"
            f"{counts['n_schools_all_2026'].median():.1f} 所，"
            f"{counts['school_count_change'].lt(0).sum()}/{len(counts)} 省下降。"
            "该变化包含来源覆盖差异，不能解释为学校停招。"
        )

    rows.append("")
    rows.append("### 留一省稳健性")
    for track in CLINICAL_TRACKS:
        subset = lovo[
            lovo["track"].eq(track)
            & lovo["outcome"].eq("all_change")
        ]
        rows.append(
            f"- **{TRACKS[track]['label']}**：全样本均值 "
            f"{subset['full_mean'].iloc[0]:+.2f} 个百分点；逐省排除后的范围 "
            f"{subset['lovo_mean'].min():+.2f}～{subset['lovo_mean'].max():+.2f}，"
            f"最大值波动 {subset['difference_from_full'].abs().max():.2f} 个百分点。"
        )

    rows.append("")
    rows.append("### 院校层级梯度")
    for track in CLINICAL_TRACKS:
        subset = tier_change[tier_change["track"].eq(track)]
        values = []
        for tier in ["低位", "中位", "高位"]:
            one = subset[subset["tier"].eq(tier)]["median_change"]
            values.append(f"{tier} {one.median():+.2f}")
        rows.append(
            f"- **{TRACKS[track]['label']}**：省级层级变化中位数为"
            f"{'，'.join(values)} 个百分点；"
            f"共 {subset['province'].nunique()} 省满足每省至少6所共同院校。"
        )

    rows.append("")
    rows.append("### 固定同校累计变化")
    for track in CLINICAL_TRACKS:
        subset = cumulative[cumulative["track"].eq(track)]
        final = subset[subset["year"].eq(2026)].set_index("province")[
            "cumulative_change"
        ]
        rows.append(
            f"- **{TRACKS[track]['label']}**：2026年相对2021年的省级累计变化"
            f"中位数为 {final.median():+.2f} 个百分点，"
            f"25%–75%范围为 {final.quantile(0.25):+.2f}～"
            f"{final.quantile(0.75):+.2f}（{len(final)}省）。"
        )

    text = """# 首轮趋势分析结果

这是正式分析的第一个可复现版本。图表使用 2017–2026 合并面板；2026 年 31 个省年共同纳入。六个省级官方专业表与其余 25 个省级单位的公开归档专业数据共同进入正式分析，来源在图上标明。

## 图表口径

- 专业池百分位越高，表示录取竞争越强；热图颜色越深，也表示竞争越强。
- 热图灰色表示该省该年没有可计算的专业池百分位。310/310 表示省年框架中有目标专业记录，不表示每个单元都有完整专业池。
- 2026 年山东、辽宁、河北、浙江、重庆、贵州使用省级官方专业表；其余 25 个省级单位使用公开归档专业数据。
- 相对变化热图以各省首个可用年份为 0，用于观察方向，不把不同基线的绝对百分点当作同尺度比较。
- 同校平衡样本固定两年都出现或 2021–2026 每年都出现的院校，用于检查总体均值的院校构成敏感性。
- 学制位次差分别展示同省配对与同校配对；同校版本控制院校层级构成。
- 同校内部变化分布使用纯小提琴展示逐校配对密度，并直接标注中位数与下降比例。
- 可计算院校数、留一省稳健性、院校层级梯度和固定同校累计变化均使用临床类别；2026 院校数变化首先作为来源覆盖诊断。

## 年度均值

""" + "\n".join(rows) + """

## 当前能下的结论

- 2025 年临床医学已经出现跨省同步下移，2026 年合并全国数据后跌幅进一步扩大。
- 2026 年全国合并均值对学校构成高度敏感。同省同校样本的跌幅显著小于全部院校样本，因此“全国均值下降”不能直接解释为所有原有院校同步降温。
- 同一批院校内部仍有广泛下移：全部临床和五年制的逐校变化中位数约为 -2.5 和 -3.0 个百分点，约 73% 的学校—省配对环境下降。省级均值降幅较小，说明统计单位会改变结果表述。
- 2026年可计算院校数明显减少，且多数省份下降；这与公开归档层覆盖较窄一致。全部院校均值变化同时包含真实录取变化和数据覆盖变化，不能把院校数减少写成实际停招。
- 逐省留一法没有显示单一省份主导总体均值；院校层级梯度可作为补充观察，但层级是省内相对位置，不作学校质量或政策归因。
- 五年制和八年制需要分开看。八年制的省级覆盖远小于五年制和全部临床，因此其曲线用于识别精英层的相对稳定性，不用于代表全体医学报考热度。
- 同省口径的八年制减五年制位次差在 2026 年为 34.2 个百分点；同校口径仍为 1.6 个百分点，正值说明同一所学校内八年制录取位置略高于五年制。两组结果的差异主要反映院校层级构成，不能把同省差值全部解释为学制本身的溢价。
- 2026 年官方省级专业表与公开归档数据都显示临床方向向下，但两层绝对水平和跌幅不同。全国合并均值反映“共同方向”，跌幅大小需要结合来源敏感性表解释。

## 尚未完成

- 招生计划数量、计划加权趋势和扩招贡献。
- 院校、省份和年份的正式多层模型与分段趋势模型。
- 临床与口腔、麻醉、影像、护理等医学内部专业的机会成本比较。
"""
    (ROOT / "ANALYSIS_RESULTS_FIRST_PASS.md").write_text(text, encoding="utf-8")


def sync_report_figures() -> None:
    REPORT_FIGURES.mkdir(parents=True, exist_ok=True)
    for name in CORE_REPORT_FIGURES:
        shutil.copy2(FIGURES / name, REPORT_FIGURES / name)


def main() -> None:
    configure_matplotlib()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    frame = read_panel()
    school_layer, province_layer = build_analysis_layer(frame)
    coverage = build_track_coverage(province_layer)
    curve_summary = build_curve_summary(province_layer)
    change_table = build_change_table(province_layer)
    metric_comparison = build_metric_comparison(province_layer)
    year_change = build_year_change_summary(province_layer)
    slogan_tests = build_slogan_tests(year_change)
    source_sensitivity = build_2026_source_sensitivity(province_layer)
    balanced_recent = build_recent_balanced_change(school_layer, province_layer)
    balanced_long = build_long_balanced_panel(school_layer, province_layer)
    premium_province, premium_school = build_track_premium(
        province_layer, school_layer
    )
    school_change_pairs = build_school_change_pairs(
        school_layer, balanced_recent
    )
    school_count_change = build_school_count_change(balanced_recent)
    lovo = build_leave_one_out(balanced_recent)
    tier_change = build_school_tier_change(school_change_pairs)
    cumulative = build_cumulative_change(balanced_long)

    school_layer.to_csv(
        OUTPUT / "analysis_school_year.csv", index=False, encoding="utf-8-sig"
    )
    province_layer.to_csv(
        OUTPUT / "analysis_province_year.csv", index=False, encoding="utf-8-sig"
    )
    coverage.to_csv(
        OUTPUT / "analysis_track_coverage.csv", index=False, encoding="utf-8-sig"
    )
    curve_summary.to_csv(
        OUTPUT / "analysis_curve_summary.csv", index=False, encoding="utf-8-sig"
    )
    change_table.to_csv(
        OUTPUT / "analysis_change_2017_2026.csv", index=False, encoding="utf-8-sig"
    )
    metric_comparison.to_csv(
        OUTPUT / "analysis_metric_comparison.csv", index=False, encoding="utf-8-sig"
    )
    year_change.to_csv(
        OUTPUT / "analysis_year_change_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    slogan_tests.to_csv(
        OUTPUT / "analysis_slogan_tests.csv", index=False, encoding="utf-8-sig"
    )
    source_sensitivity.to_csv(
        OUTPUT / "analysis_2026_source_sensitivity.csv",
        index=False,
        encoding="utf-8-sig",
    )
    balanced_recent.to_csv(
        OUTPUT / "analysis_balanced_change_2025_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    balanced_long.to_csv(
        OUTPUT / "analysis_balanced_trend_2021_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    premium_province.to_csv(
        OUTPUT / "analysis_track_premium_province.csv",
        index=False,
        encoding="utf-8-sig",
    )
    premium_school.to_csv(
        OUTPUT / "analysis_track_premium_school.csv",
        index=False,
        encoding="utf-8-sig",
    )
    school_change_pairs.to_csv(
        OUTPUT / "analysis_school_change_2025_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    school_count_change.to_csv(
        OUTPUT / "analysis_school_count_change_2025_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    lovo.to_csv(
        OUTPUT / "analysis_lopo_robustness_2025_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    tier_change.to_csv(
        OUTPUT / "analysis_school_tier_change_2025_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )
    cumulative.to_csv(
        OUTPUT / "analysis_cumulative_change_2021_2026.csv",
        index=False,
        encoding="utf-8-sig",
    )

    draw_heatmaps(province_layer)
    draw_province_curves(province_layer)
    draw_average_curves(curve_summary)
    draw_annual_change_figure(year_change)
    draw_metric_robustness(curve_summary)
    draw_recent_balanced_change(balanced_recent)
    draw_long_balanced_panel(balanced_long)
    draw_track_premium(premium_province, premium_school)
    draw_school_change_distribution(school_change_pairs)
    draw_school_count_change(school_count_change)
    draw_leave_one_out(lovo)
    draw_school_tier_gradient(tier_change)
    draw_cumulative_change(cumulative)
    sync_report_figures()
    write_methods()
    write_preliminary_findings(
        curve_summary,
        change_table,
        year_change,
        slogan_tests,
        source_sensitivity,
        balanced_recent,
        balanced_long,
        premium_province,
        premium_school,
        school_change_pairs,
        school_count_change,
        lovo,
        tier_change,
        cumulative,
    )

    print(f"Wrote analysis layer: {len(province_layer):,} province-track-metric rows")
    print(f"Wrote school layer: {len(school_layer):,} rows")
    print(
        f"Wrote balanced layer: {len(balanced_recent):,} recent rows, "
        f"{len(balanced_long):,} long-panel rows"
    )
    print(
        f"Wrote premium layer: {len(premium_province):,} province pairs, "
        f"{len(premium_school):,} school pairs"
    )
    print(
        f"Wrote robustness layer: {len(school_change_pairs):,} school-change pairs, "
        f"{len(tier_change):,} province-tier rows, {len(lovo):,} LOPO rows"
    )
    print(f"Wrote figures: {len(CORE_REPORT_FIGURES)} report figures")


if __name__ == "__main__":
    main()
