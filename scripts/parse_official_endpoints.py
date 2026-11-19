"""Parse official 2025 and 2026 endpoint tables into a common schema.

The script keeps the full offer pool long enough to calculate the same
within-pool admission percentile used by the national analysis. It then writes
the clinical subset for audit and later linkage. Parsing is checked against the
2026 source-manifest row counts and the clinical target counts already
reconciled in the public repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd
import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "official_endpoints"
SUMMARY = OUTPUT / "official_endpoint_parse_summary.json"
CLINICAL_OUTPUT = OUTPUT / "clinical_official_endpoints_2025_2026.csv"

EXPECTED_PARSED_ROWS = {
    ("山东", 2025): 21_380,
    ("河北", 2025): 19_279,
    ("辽宁", 2025): 10_969,
    ("重庆", 2025): 11_582,
    ("浙江", 2025): 17_890,
    ("浙江", 2026): 18_543,
    ("山东", 2026): 23_852,
    ("河北", 2026): 20_664,
    ("辽宁", 2026): 11_628,
    ("重庆", 2026): 12_508,
}

EXPECTED_CLINICAL_ROWS = {
    ("山东", 2025): 218,
    ("河北", 2025): 201,
    ("辽宁", 2025): 149,
    ("贵州", 2025): 184,
    ("重庆", 2025): 172,
    ("浙江", 2025): 228,
    ("山东", 2026): 235,
    ("河北", 2026): 209,
    ("浙江", 2026): 215,
    ("辽宁", 2026): 154,
    ("贵州", 2026): 178,
    ("重庆", 2026): 180,
}

SOURCE_FILES = {
    ("山东", 2025): "sdzk_2025_regular_batch.xls",
    ("河北", 2025): "hebeea_2025_physics_regular_batch.xlsx",
    ("辽宁", 2025): "lnzsks_2025_physics_regular_batch.csv",
    ("贵州", 2025): "guizhou_2025_physics_regular_batch.pdf",
    ("重庆", 2025): "cqksy_2025_physics_regular_batch.pdf",
    ("浙江", 2025): "zjzs_2025_first_segment.xls",
    ("山东", 2026): "sdzk_2026_regular_batch.xls",
    ("河北", 2026): "hebeea_2026_regular_batch_physics.xlsx",
    ("辽宁", 2026): "lnzsks_2026_regular_batch_physics.xlsx",
    ("贵州", 2026): "guizhou_2026_regular_batch_physics.pdf",
    ("重庆", 2026): "cqksy_2026_regular_batch_physics.pdf",
    ("浙江", 2026): "zjzs_2026_first_segment.xls",
}

COMMON_COLUMNS = [
    "province",
    "year",
    "batch",
    "university_code",
    "university",
    "major_code",
    "major",
    "subject_req",
    "plan_count",
    "admit_count",
    "min_score",
    "min_rank",
    "source_file",
    "source_sha256",
    "source_sequence",
    "source_row",
]

WATERMARK_LINES = re.compile(r"^(?:市|庆|院|试|考|育|教|重)$")


def clean_text(value: object) -> str:
    """Remove PDF watermark-only lines while preserving institution names."""

    text = str(value or "").replace("\r", "\n").strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if not WATERMARK_LINES.fullmatch(line)]
    return "".join(lines).replace("\u3000", "").strip()


def numeric(value: object) -> float:
    text = clean_text(value)
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else float("nan")


def strict_numeric(value: object) -> float:
    text = clean_text(value)
    return float(text) if re.fullmatch(r"\d+(?:\.\d+)?", text) else float("nan")


def split_coded_name(value: object) -> tuple[str, str]:
    text = clean_text(value)
    match = re.match(r"^([0-9A-Za-z]+)\s*(.*)$", text)
    if not match:
        return "", text
    return match.group(1), match.group(2).strip()


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=COMMON_COLUMNS)


def finish_rows(
    rows: list[dict[str, object]],
    province: str,
    year: int,
    path: Path,
    batch: str,
) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return empty_frame()
    frame["province"] = province
    frame["year"] = year
    frame["batch"] = batch
    frame["source_file"] = path.name
    frame["source_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for column in COMMON_COLUMNS:
        if column not in frame:
            frame[column] = pd.NA
    frame["source_row"] = pd.to_numeric(frame["source_row"], errors="coerce")
    for column in ["plan_count", "admit_count", "min_score", "min_rank"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[COMMON_COLUMNS].copy()
    frame = frame[
        frame["university"].fillna("").astype(str).str.strip().ne("")
        & frame["major"].fillna("").astype(str).str.strip().ne("")
        & (
            frame["min_score"].gt(0)
            | frame["min_rank"].gt(0)
        )
    ]
    return frame.reset_index(drop=True)


def parse_shandong(path: Path, year: int) -> pd.DataFrame:
    frame = pd.read_excel(path, header=1, dtype=str)
    frame.columns = [
        "major_coded",
        "university_coded",
        "count_or_subject_req",
        "min_rank",
    ]
    rows = []
    for source_row, row in enumerate(frame.itertuples(index=False), start=3):
        major_code, major = split_coded_name(row.major_coded)
        university_code, university = split_coded_name(row.university_coded)
        count_or_subject = clean_text(row.count_or_subject_req)
        rows.append(
            {
                "university_code": university_code,
                "university": university,
                "major_code": major_code,
                "major": major,
                "subject_req": (
                    count_or_subject
                    if not re.fullmatch(r"\d+(?:\.\d+)?", count_or_subject)
                    else ""
                ),
                "plan_count": (
                    numeric(count_or_subject)
                    if year == 2025
                    else float("nan")
                ),
                "min_rank": strict_numeric(row.min_rank),
                "source_row": source_row,
            }
        )
    return finish_rows(rows, "山东", year, path, "普通类常规批")


def parse_hebei(path: Path, year: int) -> pd.DataFrame:
    frame = pd.read_excel(path, header=None, dtype=str)
    rows = []
    for source_row, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        if source_row <= 5 or len(row) < 5:
            continue
        university_code = clean_text(row[0])
        if not re.fullmatch(r"[0-9A-Za-z]{3,4}", university_code):
            continue
        rows.append(
            {
                "university_code": university_code,
                "university": clean_text(row[1]),
                "major_code": clean_text(row[2]),
                "major": clean_text(row[3]),
                "min_score": numeric(row[4]),
                "source_row": source_row,
            }
        )
    return finish_rows(rows, "河北", year, path, "普通类本科批")


def parse_liaoning(path: Path, year: int) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, header=None, dtype=str)
    else:
        frame = pd.read_excel(path, header=None, dtype=str)
    rows = []
    for source_row, row in enumerate(frame.itertuples(index=False, name=None), start=1):
        if source_row <= 5 or len(row) < 5:
            continue
        university_code = clean_text(row[0])
        if not re.fullmatch(r"[0-9A-Za-z]{3,4}", university_code):
            continue
        rows.append(
            {
                "university_code": university_code,
                "university": clean_text(row[1]),
                "major_code": clean_text(row[2]),
                "major": clean_text(row[3]),
                "min_score": numeric(row[4]),
                "source_row": source_row,
            }
        )
    return finish_rows(rows, "辽宁", year, path, "普通类本科批")


def parse_zhejiang(path: Path, year: int) -> pd.DataFrame:
    frame = pd.read_excel(path, header=0, dtype=str)
    frame.columns = [
        "university_code",
        "university",
        "major_code",
        "major",
        "plan_count",
        "min_score",
        "min_rank",
    ]
    rows = []
    for source_row, row in enumerate(frame.itertuples(index=False), start=2):
        rows.append(
            {
                "university_code": clean_text(row.university_code),
                "university": clean_text(row.university),
                "major_code": clean_text(row.major_code),
                "major": clean_text(row.major),
                "plan_count": numeric(row.plan_count),
                "min_score": numeric(row.min_score),
                "min_rank": numeric(row.min_rank),
                "source_row": source_row,
            }
        )
    return finish_rows(rows, "浙江", year, path, "普通类第一段")


def parse_guizhou(path: Path, year: int) -> pd.DataFrame:
    rows = []
    sequence_values = []
    with pdfplumber.open(path) as pdf:
        source_row = 0
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    if not raw or not str(raw[0] or "").strip().isdigit():
                        continue
                    source_row += 1
                    sequence = int(str(raw[0]).strip())
                    sequence_values.append(sequence)
                    if len(raw) >= 10:
                        values = {
                            "university_code": clean_text(raw[1]),
                            "university": clean_text(raw[2]),
                            "major_code": clean_text(raw[3]),
                            "major": clean_text(raw[4]),
                            "plan_count": numeric(raw[6]),
                            "admit_count": numeric(raw[7]),
                            "min_score": numeric(raw[8]),
                            "min_rank": numeric(raw[9]),
                        }
                    elif len(raw) >= 9:
                        values = {
                            "university_code": clean_text(raw[1]),
                            "university": clean_text(raw[2]),
                            "major_code": clean_text(raw[3]),
                            "major": clean_text(raw[4]),
                            "admit_count": numeric(raw[6]),
                            "min_score": numeric(raw[7]),
                            "min_rank": numeric(raw[8]),
                        }
                    else:
                        continue
                    values["source_sequence"] = sequence
                    values["source_row"] = source_row
                    rows.append(values)
    frame = finish_rows(rows, "贵州", year, path, "普通类本科批")
    frame.attrs["source_sequence_values"] = sequence_values
    return frame


def parse_chongqing(path: Path, year: int) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        source_row = 0
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw in table:
                    if not raw:
                        continue
                    university_code = clean_text(raw[0])
                    if not re.fullmatch(r"[0-9A-Za-z]{3,4}", university_code):
                        continue
                    source_row += 1
                    if len(raw) < 5:
                        continue
                    rows.append(
                        {
                            "university_code": university_code,
                            "university": clean_text(raw[1]),
                            "major_code": clean_text(raw[2]),
                            "major": clean_text(raw[3]),
                            "min_score": numeric(raw[4]),
                            "source_row": source_row,
                        }
                    )
    return finish_rows(rows, "重庆", year, path, "普通类本科批")


PARSERS = {
    "山东": parse_shandong,
    "河北": parse_hebei,
    "辽宁": parse_liaoning,
    "贵州": parse_guizhou,
    "重庆": parse_chongqing,
    "浙江": parse_zhejiang,
}


def add_offer_percentile(frame: pd.DataFrame) -> pd.DataFrame:
    output = []
    for (_, _), group in frame.groupby(["province", "year"], sort=False):
        group = group.copy()
        n_records = int(
            (
                group["min_rank"].notna()
                | group["min_score"].notna()
            ).sum()
        )
        group["pool_n_records"] = n_records
        group["admission_percentile"] = pd.Series(
            index=group.index,
            dtype=float,
        )
        if group["min_rank"].notna().any():
            n_rank_records = int(group["min_rank"].notna().sum())
            rank_position = group["min_rank"].rank(
                method="average",
                ascending=True,
            )
            rank_mask = group["min_rank"].notna()
            group.loc[rank_mask, "pool_rank_position"] = rank_position
            group.loc[rank_mask, "pool_n_records"] = n_rank_records
            group.loc[rank_mask, "admission_percentile"] = (
                (n_rank_records - rank_position[rank_mask] + 1)
                / n_rank_records
                * 100
            )
            score_mask = group["min_rank"].isna() & group["min_score"].notna()
            score_position = group["min_score"].rank(
                method="average",
                ascending=True,
            )
            group.loc[score_mask, "pool_rank_position"] = score_position
            group.loc[score_mask, "admission_percentile"] = (
                score_position[score_mask] / n_records * 100
            )
        else:
            score_position = group["min_score"].rank(
                method="average",
                ascending=True,
            )
            group["pool_rank_position"] = score_position
            group["admission_percentile"] = (
                score_position / n_records * 100
            )
        output.append(group)
    if not output:
        return frame.assign(
            pool_rank_position=pd.Series(dtype=float),
            pool_n_records=pd.Series(dtype=int),
            admission_percentile=pd.Series(dtype=float),
        )
    return pd.concat(output, ignore_index=True)


def split_major_note(major: str) -> tuple[str, str]:
    text = clean_text(major).replace("（", "(").replace("）", ")")
    match = re.match(r"^([^(]+)(.*)$", text)
    if not match:
        return text, ""
    return match.group(1).strip(), match.group(2).strip()


def identify_clinical_track(major: str) -> str:
    text = clean_text(major).replace(" ", "")
    if re.search(r"八年制|本博连读|8年制", text):
        return "explicit_eight_year"
    if re.search(r"5\+3|五加三|5加3", text):
        return "explicit_5plus3"
    if re.search(r"五年制", text):
        return "explicit_five_year"
    return "ordinary_five_year_likely"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory containing the official endpoint source files.",
    )
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    parsed = []
    summary: dict[str, object] = {"sources": []}
    for (province, year), filename in SOURCE_FILES.items():
        path = args.input_dir / filename
        if not path.exists():
            summary["sources"].append(
                {
                    "province": province,
                    "year": year,
                    "file": filename,
                    "status": "missing",
                }
            )
            continue
        frame = PARSERS[province](path, year)
        frame = add_offer_percentile(frame)
        major_parts = frame["major"].map(split_major_note)
        frame["major_base"] = major_parts.map(lambda value: value[0])
        frame["major_note"] = major_parts.map(lambda value: value[1])
        frame["clinical_track"] = frame["major"].map(identify_clinical_track)
        frame["is_clinical"] = frame["major_base"].str.startswith("临床医学")
        clinical = frame[frame["is_clinical"]].copy()
        parsed.append(clinical)

        expected_parsed = EXPECTED_PARSED_ROWS.get((province, year))
        expected_clinical = EXPECTED_CLINICAL_ROWS.get((province, year))
        sequence_values = pd.Series(
            frame.attrs.get(
                "source_sequence_values",
                pd.to_numeric(
                    frame["source_sequence"], errors="coerce"
                ).dropna(),
            )
        )
        sequence_validated = False
        sequence_min = None
        sequence_max = None
        sequence_gaps = None
        if not sequence_values.empty:
            sequence_min = int(sequence_values.min())
            sequence_max = int(sequence_values.max())
            sequence_gaps = sequence_max - sequence_min + 1 - sequence_values.nunique()
            sequence_validated = (
                sequence_values.is_unique
                and sequence_min == 1
                and sequence_gaps == 0
            )
        status = "parsed"
        if (
            expected_parsed is not None
            and len(frame) != expected_parsed
            and not sequence_validated
        ):
            status = "parsed_row_count_mismatch"
        clinical_delta = (
            int(len(clinical) - expected_clinical)
            if expected_clinical is not None
            else None
        )
        if (
            expected_clinical is not None
            and len(clinical) < expected_clinical
        ):
            status = "parsed_with_panel_rows_missing"
        elif (
            expected_clinical is not None
            and len(clinical) > expected_clinical
        ):
            status = "parsed_with_panel_rows_unmatched"
        numeric_codes = (
            frame["university_code"]
            .fillna("")
            .astype(str)
            .str.fullmatch(r"\d{4}")
        )
        summary["sources"].append(
            {
                "province": province,
                "year": year,
                "file": filename,
                "sha256": frame["source_sha256"].iloc[0],
                "parsed_rows": int(len(frame)),
                "expected_parsed_rows": expected_parsed,
                "numeric_four_digit_code_rows": int(numeric_codes.sum()),
                "clinical_rows": int(len(clinical)),
                "expected_clinical_rows": expected_clinical,
                "clinical_rows_vs_panel": clinical_delta,
                "sequence_min": sequence_min,
                "sequence_max": sequence_max,
                "sequence_gaps": sequence_gaps,
                "sequence_validated": sequence_validated,
                "admission_metric_rows": int(frame["admission_percentile"].notna().sum()),
                "metric_basis": (
                    "min_rank"
                    if frame["min_rank"].notna().any()
                    else "min_score"
                ),
                "status": status,
            }
        )

    if not parsed:
        raise RuntimeError("No official endpoint sources were parsed.")

    combined = pd.concat(parsed, ignore_index=True)
    combined = combined.sort_values(
        ["year", "province", "university", "major", "source_row"]
    )
    combined.to_csv(CLINICAL_OUTPUT, index=False, encoding="utf-8-sig")
    summary["clinical_output"] = str(CLINICAL_OUTPUT.relative_to(ROOT))
    summary["clinical_output_rows"] = int(len(combined))
    summary["all_parser_checks_passed"] = all(
        not str(source.get("status", "")).startswith(
            ("missing", "parsed_row_count_mismatch")
        )
        for source in summary["sources"]
    )
    summary["all_panel_reconciliations_passed"] = all(
        source.get("clinical_rows_vs_panel") == 0
        for source in summary["sources"]
    )
    SUMMARY.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_parser_checks_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
