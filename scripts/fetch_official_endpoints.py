"""Download and verify official clinical-medicine endpoint sources."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import urllib.request
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "official_endpoints" / "source_manifest.csv"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 clinical-medicine-source-audit"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def ps_quote(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def export_liaoning_2025_csv(source: Path, destination: Path) -> None:
    """Export the Office compound workbook with its misleading .xlsx suffix."""

    script = f"""
$ErrorActionPreference = 'Stop'
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
try {{
    $workbook = $excel.Workbooks.Open({ps_quote(source)}, 0, $true)
    $workbook.SaveAs({ps_quote(destination)}, 62)
    $workbook.Close($false)
}}
finally {{
    $excel.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
}}
"""
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    manifest = pd.read_csv(MANIFEST, dtype=str)
    failures = []
    for row in manifest.itertuples(index=False):
        destination = args.output_dir / row.file_name
        if not destination.exists():
            print(f"Downloading {row.province} {row.year}: {row.file_name}")
            download(row.attachment_url, destination)
        size_ok = destination.stat().st_size == int(row.file_size)
        actual_hash = sha256(destination)
        hash_ok = actual_hash == row.sha256
        print(
            f"{row.province} {row.year}: size={size_ok}, "
            f"sha256={hash_ok}, rows_file={destination.name}"
        )
        if not size_ok or not hash_ok:
            failures.append(
                {
                    "province": row.province,
                    "year": row.year,
                    "file": row.file_name,
                    "expected_size": int(row.file_size),
                    "actual_size": destination.stat().st_size,
                    "expected_sha256": row.sha256,
                    "actual_sha256": actual_hash,
                }
            )
        if row.file_name == "lnzsks_2025_physics_regular_batch.xlsx":
            csv_path = destination.with_suffix(".csv")
            if not csv_path.exists() or csv_path.stat().st_size == 0:
                print(f"Exporting Office compound workbook to {csv_path.name}")
                export_liaoning_2025_csv(destination, csv_path)
    if failures:
        raise SystemExit(f"Source verification failed: {failures}")


if __name__ == "__main__":
    main()
