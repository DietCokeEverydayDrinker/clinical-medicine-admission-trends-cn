"""Validate parsed official endpoint outputs and their known audit deltas."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from build_official_endpoint_reconciliation import build_reconciliation


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "official_endpoints"
SUMMARY = OUTPUT / "official_endpoint_parse_summary.json"
CLINICAL = OUTPUT / "clinical_official_endpoints_2025_2026.csv"
VALIDATION = OUTPUT / "official_endpoint_validation.json"

EXPECTED_CLINICAL_ROWS = {
    ("山东", 2025): 218,
    ("河北", 2025): 201,
    ("辽宁", 2025): 149,
    ("贵州", 2025): 184,
    ("重庆", 2025): 171,
    ("浙江", 2025): 228,
    ("山东", 2026): 235,
    ("河北", 2026): 209,
    ("辽宁", 2026): 154,
    ("贵州", 2026): 189,
    ("重庆", 2026): 183,
    ("浙江", 2026): 215,
}

EXPECTED_PANEL_DELTAS = {
    ("贵州", 2026): 11,
    ("重庆", 2025): -1,
    ("重庆", 2026): 3,
}


def main() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    clinical = pd.read_csv(
        CLINICAL,
        dtype={"university_code": str, "major_code": str},
    )
    assert summary["all_parser_checks_passed"], "Parser checks did not pass."
    assert len(summary["sources"]) == 12, "Expected 12 official sources."
    assert not summary["all_panel_reconciliations_passed"]

    observed_rows = {}
    observed_deltas = {}
    for source in summary["sources"]:
        key = (source["province"], int(source["year"]))
        observed_rows[key] = int(source["clinical_rows"])
        if source["clinical_rows_vs_panel"] not in (None, 0):
            observed_deltas[key] = int(source["clinical_rows_vs_panel"])
    assert observed_rows == EXPECTED_CLINICAL_ROWS
    assert observed_deltas == EXPECTED_PANEL_DELTAS

    key = [
        "province",
        "year",
        "university_code",
        "major_code",
    ]
    assert not clinical.duplicated(key).any(), "Duplicate official offer keys."
    assert clinical["admission_percentile"].between(0, 100).all()
    assert clinical["admission_percentile"].notna().all()
    assert clinical["clinical_track"].isin(
        {
            "ordinary_five_year_likely",
            "explicit_five_year",
            "explicit_5plus3",
            "explicit_eight_year",
        }
    ).all()
    _, reconciliation = build_reconciliation()
    assert reconciliation["total_official_only_rows"] == 14
    assert reconciliation["total_panel_only_rows"] == 1

    result = {
        "sources": len(summary["sources"]),
        "clinical_rows": int(len(clinical)),
        "unique_offer_keys": int(clinical[key].drop_duplicates().shape[0]),
        "panel_reconciliation_deltas": {
            f"{province}_{year}": delta
            for (province, year), delta in observed_deltas.items()
        },
        "row_reconciliation": {
            "official_only": reconciliation["total_official_only_rows"],
            "panel_only": reconciliation["total_panel_only_rows"],
        },
        "status": "passed",
    }
    VALIDATION.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
