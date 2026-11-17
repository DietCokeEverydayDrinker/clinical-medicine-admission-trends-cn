"""Validate the report structure, local links, figures, and wording boundary."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
REPORT = ROOT / "REPORT.md"
FIGURE_ROOT = OUTPUT / "figures"
REPORT_FIGURE_ROOT = OUTPUT / "report_figures"

CORE_FIGURES = [
    "fig_heatmap_all_clinical.png",
    "fig_average_curves.png",
    "fig_annual_changes.png",
    "fig_balanced_change_2025_2026.png",
    "fig_school_change_distribution_2025_2026.png",
    "fig_cumulative_change_2021_2026.png",
    "fig_track_premium.png",
    "fig_school_tier_gradient_2025_2026.png",
]

REQUIRED_SECTIONS = [
    "# 临床医学录取竞争位置变化：2017–2026",
    "## 摘要",
    "## 1. 研究缘起与问题",
    "## 2. 数据来源与采集方法",
    "## 3. 指标与统计方法",
    "## 4. 数据图景",
    "## 5. 结论与解释边界",
    "## 6. 可复现材料",
    "## 7. 使用边界与继续研究",
]

FORBIDDEN_CLAIMS = [
    "临床医学行业已经崩溃",
    "医学职业没有前景",
    "临床医学就业已经崩塌",
    "所有学校都在同步暴跌",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_targets(text: str) -> list[str]:
    return [
        target
        for target in re.findall(r"\]\(([^)]+)\)", text)
        if not target.startswith(("http://", "https://", "#"))
    ]


def main() -> None:
    assert REPORT.exists(), "REPORT.md is missing"
    text = REPORT.read_text(encoding="utf-8")
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    audit_text = (ROOT / "DATA_QUALITY_AUDIT.md").read_text(encoding="utf-8")
    figure_set_text = (ROOT / "REPORT_FIGURE_SET.md").read_text(encoding="utf-8")

    for section in REQUIRED_SECTIONS:
        assert section in text, section

    public_texts = [text, readme_text, audit_text, figure_set_text]
    for phrase in FORBIDDEN_CLAIMS:
        assert all(phrase not in item for item in public_texts), phrase

    assert "2025 年是临床医学本科录取竞争位置一个清晰的下移节点" in text
    assert "不能据此判断职业前景、就业质量或行业寿命" in text
    assert "全部院校均值变化 -10.0 个百分点，固定同校变化 -0.8" in text
    assert "变化中位数 -2.52 个百分点，73.7% 的配对下降" in text
    expected_images = {
        f"output/report_figures/{name}" for name in CORE_FIGURES
    }
    image_targets = set(re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text))
    assert image_targets == expected_images
    assert text.count("![") == len(CORE_FIGURES)

    for target in local_targets(text):
        path = (ROOT / target).resolve()
        assert path.exists(), f"broken local link: {target}"

    readme_targets = local_targets(readme_text)
    for target in readme_targets:
        path = (ROOT / target).resolve()
        assert path.exists(), f"broken README link: {target}"

    for name in CORE_FIGURES:
        source = FIGURE_ROOT / name
        report_copy = REPORT_FIGURE_ROOT / name
        assert source.exists(), name
        assert report_copy.exists(), name
        assert sha256(source) == sha256(report_copy), name

    source_rows = (
        (OUTPUT / "clinical_source_manifest.csv")
        .read_text(encoding="utf-8-sig")
        .count("\n")
    )
    result = {
        "status": "passed",
        "report": REPORT.name,
        "sections": len(REQUIRED_SECTIONS),
        "core_figures": len(CORE_FIGURES),
        "local_links_checked": len(set(local_targets(text))),
        "readme_links_checked": len(set(readme_targets)),
        "source_manifest_rows": source_rows - 1,
    }
    (OUTPUT / "report_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
