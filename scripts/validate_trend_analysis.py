"""Validate the merged trend-analysis layer and generated figures."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
FIGURES = OUTPUT / "figures"


def read_csv(name: str) -> list[dict[str, str]]:
    with (OUTPUT / name).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    province = read_csv("analysis_province_year.csv")
    coverage = read_csv("analysis_track_coverage.csv")
    curves = read_csv("analysis_curve_summary.csv")
    year_change = read_csv("analysis_year_change_summary.csv")
    slogans = read_csv("analysis_slogan_tests.csv")
    source_sensitivity = read_csv("analysis_2026_source_sensitivity.csv")
    balanced_recent = read_csv("analysis_balanced_change_2025_2026.csv")
    balanced_long = read_csv("analysis_balanced_trend_2021_2026.csv")
    premium_province = read_csv("analysis_track_premium_province.csv")
    premium_school = read_csv("analysis_track_premium_school.csv")
    school_change = read_csv("analysis_school_change_2025_2026.csv")
    school_count = read_csv("analysis_school_count_change_2025_2026.csv")
    lopo = read_csv("analysis_lopo_robustness_2025_2026.csv")
    school_tiers = read_csv("analysis_school_tier_change_2025_2026.csv")
    cumulative = read_csv("analysis_cumulative_change_2021_2026.csv")

    assert province, "province-year analysis layer is empty"
    assert coverage, "track coverage is empty"
    assert curves, "curve summary is empty"
    assert year_change, "year-change summary is empty"
    assert slogans, "slogan tests are empty"
    assert source_sensitivity, "2026 source sensitivity is empty"
    assert balanced_recent, "recent balanced panel is empty"
    assert balanced_long, "long balanced panel is empty"
    assert premium_province, "province track premium is empty"
    assert premium_school, "school track premium is empty"
    assert school_change, "school change pairs are empty"
    assert school_count, "school count change is empty"
    assert lopo, "leave-one-province-out table is empty"
    assert school_tiers, "school tier table is empty"
    assert cumulative, "cumulative change table is empty"

    tracks = {"all_clinical", "five_year", "eight_year"}
    metrics = {"admission_percentile", "candidate_percentile"}
    assert {row["track"] for row in province} == tracks
    assert {row["metric"] for row in province} == metrics
    assert len(province) == 1604

    for row in province:
        value = row["value"]
        if value:
            assert 0 <= float(value) <= 100
        if row["meets_min_schools"] == "True":
            assert int(row["n_schools"]) >= 3

    expected_min_school_coverage = {
        ("all_clinical", "2026"): 30,
        ("five_year", "2026"): 30,
        ("eight_year", "2026"): 8,
    }
    for (track, year), expected in expected_min_school_coverage.items():
        count = sum(
            1
            for row in province
            if row["track"] == track
            and row["metric"] == "admission_percentile"
            and row["year"] == year
            and row["meets_min_schools"] == "True"
        )
        assert count == expected, (track, year, count, expected)

    curve_keys = {(row["track"], row["metric"]) for row in curves}
    assert curve_keys == {(track, metric) for track in tracks for metric in metrics}
    for key in curve_keys:
        years = {
            int(row["year"])
            for row in curves
            if (row["track"], row["metric"]) == key
        }
        assert years == set(range(2017, 2027)), key

    assert {row["statement"] for row in slogans} == {
        "临床死于2025",
        "五年制临床死于2025",
        "临床降温在2025开始，2026构成更强年度断裂",
    }
    assert any(
        row["source_group_2026"] == "ALL" for row in source_sensitivity
    )
    assert len(balanced_recent) == 92
    assert len(balanced_long) == 306
    assert len(premium_province) == 206
    assert len(premium_school) == 1038
    assert len(school_change) == 3073
    assert len(school_count) == 67
    assert len(lopo) == 134
    assert len(school_tiers) == 198
    assert len(cumulative) == 306

    school_change_counts = {
        track: sum(1 for row in school_change if row["track"] == track)
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert school_change_counts == {
        "all_clinical": 1542,
        "five_year": 1485,
        "eight_year": 46,
    }
    assert {row["track"] for row in school_count} == {
        "all_clinical",
        "five_year",
        "eight_year",
    }
    assert {row["outcome"] for row in lopo} == {
        "all_change",
        "balanced_change",
    }
    assert all(float(row["full_mean"]) < 0 for row in lopo)
    assert all(float(row["lovo_mean"]) < 0 for row in lopo)

    tier_provinces = {
        track: {
            row["province"]
            for row in school_tiers
            if row["track"] == track
        }
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert {track: len(values) for track, values in tier_provinces.items()} == {
        "all_clinical": 30,
        "five_year": 30,
        "eight_year": 6,
    }
    assert all(
        {row["tier"] for row in school_tiers if row["track"] == track}
        == {"低位", "中位", "高位"}
        for track in {"all_clinical", "five_year", "eight_year"}
    )

    cumulative_counts = {
        track: len([row for row in cumulative if row["track"] == track])
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert cumulative_counts == {
        "all_clinical": 156,
        "five_year": 126,
        "eight_year": 24,
    }
    assert all(int(row["year"]) in range(2021, 2027) for row in cumulative)
    assert all(
        abs(float(row["cumulative_change"])) < 1e-12
        for row in cumulative
        if row["year"] == "2021"
    )

    recent_coverage = {
        track: sum(
            1
            for row in balanced_recent
            if row["track"] == track
            and row["comparison_eligible"] == "True"
        )
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert recent_coverage == {
        "all_clinical": 30,
        "five_year": 30,
        "eight_year": 7,
    }
    long_coverage = {
        track: len(
            {
                row["province"]
                for row in balanced_long
                if row["track"] == track
            }
        )
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert long_coverage == {
        "all_clinical": 26,
        "five_year": 21,
        "eight_year": 4,
    }
    recent_eight_provinces = {
        row["province"]
        for row in balanced_recent
        if row["track"] == "eight_year"
        and row["comparison_eligible"] == "True"
    }
    assert recent_eight_provinces == {
        "河北",
        "山东",
        "辽宁",
        "重庆",
        "贵州",
        "吉林",
        "内蒙古",
    }
    long_provinces = {
        track: {
            row["province"]
            for row in balanced_long
            if row["track"] == track
        }
        for track in {"all_clinical", "five_year", "eight_year"}
    }
    assert long_provinces["all_clinical"] == {
        "安徽",
        "北京",
        "重庆",
        "福建",
        "甘肃",
        "广东",
        "广西",
        "贵州",
        "海南",
        "黑龙江",
        "湖北",
        "湖南",
        "吉林",
        "江苏",
        "辽宁",
        "内蒙古",
        "宁夏",
        "青海",
        "山东",
        "山西",
        "陕西",
        "上海",
        "四川",
        "天津",
        "新疆",
        "浙江",
    }
    assert long_provinces["five_year"] == {
        "安徽",
        "北京",
        "重庆",
        "福建",
        "广东",
        "广西",
        "贵州",
        "黑龙江",
        "湖北",
        "湖南",
        "吉林",
        "江苏",
        "辽宁",
        "内蒙古",
        "宁夏",
        "青海",
        "山东",
        "陕西",
        "四川",
        "新疆",
        "浙江",
    }
    assert long_provinces["eight_year"] == {"内蒙古", "吉林", "山东", "重庆"}

    recent_all = [
        float(row["all_change"])
        for row in balanced_recent
        if row["track"] == "all_clinical"
        and row["comparison_eligible"] == "True"
    ]
    recent_balanced = [
        float(row["balanced_change"])
        for row in balanced_recent
        if row["track"] == "all_clinical"
        and row["comparison_eligible"] == "True"
    ]
    assert abs(sum(recent_all) / len(recent_all) - (-10.007956)) < 1e-3
    assert abs(sum(recent_balanced) / len(recent_balanced) - (-0.784973)) < 1e-3

    province_gap_2026 = sorted(
        float(row["track_gap"])
        for row in premium_province
        if row["year"] == "2026"
    )
    school_gap_2026 = sorted(
        float(row["track_gap"])
        for row in premium_school
        if row["year"] == "2026"
    )
    province_median_2026 = (
        province_gap_2026[len(province_gap_2026) // 2 - 1]
        + province_gap_2026[len(province_gap_2026) // 2]
    ) / 2
    school_median_2026 = (
        school_gap_2026[len(school_gap_2026) // 2 - 1]
        + school_gap_2026[len(school_gap_2026) // 2]
    ) / 2
    assert abs(province_median_2026 - 34.18225) < 1e-6
    assert abs(school_median_2026 - 1.620525) < 1e-6

    expected_figures = [
        "fig_heatmap_all_clinical.png",
        "fig_heatmap_five_year.png",
        "fig_heatmap_eight_year.png",
        "fig_province_curves_clinical.png",
        "fig_average_curves.png",
        "fig_annual_changes.png",
        "fig_metric_robustness.png",
        "fig_balanced_change_2025_2026.png",
        "fig_balanced_trend_2021_2026.png",
        "fig_track_premium.png",
        "fig_school_change_distribution_2025_2026.png",
        "fig_school_count_change_2025_2026.png",
        "fig_lopo_robustness_2025_2026.png",
        "fig_school_tier_gradient_2025_2026.png",
        "fig_cumulative_change_2021_2026.png",
    ]
    for name in expected_figures:
        path = FIGURES / name
        assert path.exists() and path.stat().st_size > 20_000

    methods = (ROOT / "ANALYSIS_METHODS.md").read_text(encoding="utf-8")
    results = (ROOT / "ANALYSIS_RESULTS_FIRST_PASS.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "clinical_panel_2017_2026_candidate_percentile.csv" in methods
    assert "六个省级官方专业表与其余 25 个省级单位的公开归档专业数据" in results
    assert "灰色表示该省该年没有可计算的专业池百分位" in results
    assert "同校平衡样本" in methods
    assert "同校平衡样本" in results
    assert "同校口径仍为 1.6 个百分点" in results
    assert "26/21/4" in methods
    assert "三个面板使用各自纵轴" in methods
    assert "五年制" in methods
    assert "普通五年制近似" not in methods
    assert "同校内部变化分布" in methods
    assert "纯小提琴展示密度" in methods
    assert "可计算院校数" in methods
    assert "留一省稳健性" in methods
    assert "院校层级梯度" in methods
    assert "累计变化轨迹" in methods
    assert "不能直接写成学校停招" in methods
    assert "层级是省内相对录取位置，不是学校官方排名" in methods
    assert "同校内部变化分布" in results
    assert "纯小提琴" in results
    assert "可计算院校数" in results
    assert "留一省稳健性" in results
    assert "院校层级梯度" in results
    assert "固定同校" in readme
    assert "36,866" in readme
    assert "2026 年可计算院校数下降包含来源覆盖差异" in readme
    assert "院校层级是省内相对录取位置" in readme
    assert "不能代表全体临床医学" in readme

    result = {
        "status": "passed",
        "province_track_metric_rows": len(province),
        "curve_rows": len(curves),
        "year_change_rows": len(year_change),
        "slogan_test_rows": len(slogans),
        "source_sensitivity_rows": len(source_sensitivity),
        "balanced_recent_rows": len(balanced_recent),
        "balanced_long_rows": len(balanced_long),
        "premium_province_rows": len(premium_province),
        "premium_school_rows": len(premium_school),
        "school_change_rows": len(school_change),
        "school_count_change_rows": len(school_count),
        "leave_one_province_out_rows": len(lopo),
        "school_tier_rows": len(school_tiers),
        "cumulative_change_rows": len(cumulative),
        "figures": len(expected_figures),
    }
    (OUTPUT / "trend_analysis_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
