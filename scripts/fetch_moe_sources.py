"""Materialize and verify the Ministry of Education source cache.

The institution-list files are pinned to a public mirror of the ministry XLS
files. The vocational-program cache is retained because the official portal
intermittently rejects non-browser requests. Every cached source is hashed in
the manifest so the analysis can be reproduced from the committed files.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "moe"
VOCATIONAL = CACHE / "vocational_clinical"
LEGACY = ROOT / "output" / "raw" / "moe"
MANIFEST = CACHE / "moe_source_manifest.csv"

DATAXIV_COMMIT = "96abde9ea3b412ce643fbeb79f686ae65bd7e61f"
DATAXIV_REPOSITORY = "dataxiv/data-universities"

DIRECTORY_PATHS = {
    2017: "普通高等学校/2017-全国普通高等学校名单（共2631所）.xls",
    2019: "普通高等学校/2019-全国普通高等学校名单（共2688所）.xls",
    2020: "普通高等学校/2020-全国普通高等学校名单（共2740所）.xls",
    2021: "普通高等学校/2021-全国普通高等学校名单（共2756所）.xls",
    2022: "普通高等学校/2022-全国普通高等学校名单（共2759所）.xls",
    2023: "普通高等学校/2023-全国普通高等学校名单（共2820所）.xls",
    2024: "普通高等学校/2024-全国普通高等学校名单（共2868所）.xls",
    2025: "普通高等学校/2025-全国普通高等学校名单（共2919所）.xls",
    2026: "普通高等学校/2026-全国普通高等学校名单（共2952所）.xls",
}

OFFICIAL_PAGES = {
    2017: (
        "http://www.moe.gov.cn/srcsite/A03/moe_634/201706/"
        "t20170614_306900.html"
    ),
    2026: (
        "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202606/"
        "t20260618_1441074.html"
    ),
}

PROVINCE_SLUGS = (
    "AH",
    "BJ",
    "CQ",
    "FJ",
    "GD",
    "GS",
    "GX",
    "GZ",
    "HeB",
    "HeN",
    "HLJ",
    "HN",
    "HuB",
    "HuN",
    "JL",
    "JS",
    "JX",
    "LN",
    "NM",
    "NX",
    "QH",
    "SC",
    "SD",
    "SH",
    "SX",
    "SXS",
    "TJ",
    "XJ",
    "XJBT",
    "XZ",
    "YN",
    "ZJ",
)
VOCATIONAL_YEARS = tuple(range(2017, 2027))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_json_line_endings(payload: bytes) -> bytes:
    """Normalize text JSON so hashes do not depend on Git checkout settings."""
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def normalize_vocational_cache() -> int:
    changed = 0
    for path in sorted(VOCATIONAL.glob("*.json")):
        payload = path.read_bytes()
        normalized = normalize_json_line_endings(payload)
        if normalized != payload:
            path.write_bytes(normalized)
            changed += 1
    return changed


def previous_access_dates() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        return {
            row["file_path"]: row.get("accessed_date", "")
            for row in csv.DictReader(handle)
        }


def directory_source_url(mirror_path: str) -> str:
    encoded = quote(mirror_path, safe="/")
    return (
        "https://raw.githubusercontent.com/"
        f"{DATAXIV_REPOSITORY}/{DATAXIV_COMMIT}/{encoded}"
    )


def vocational_source_url(year: int, slug: str) -> str:
    query = urlencode(
        {
            "year": year,
            "province": slug,
            "majorName": "临床医学",
            "page": 1,
            "pageSize": 100,
        }
    )
    return (
        "https://zwfw.moe.gov.cn/eduSearch/api/major-register?"
        f"{query}"
    )


def download_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "clinical-medicine-admission-audit/1.0",
            "Accept": "application/vnd.github+json,application/octet-stream,*/*",
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read()


def ensure_cache_from_legacy() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for year in DIRECTORY_PATHS:
        destination = CACHE / f"moe_universities_{year}.xls"
        legacy = LEGACY / destination.name
        if not destination.exists() and legacy.exists():
            destination.write_bytes(legacy.read_bytes())
    VOCATIONAL.mkdir(parents=True, exist_ok=True)
    for source in (LEGACY / "vocational_clinical").glob("*.json"):
        destination = VOCATIONAL / source.name
        if not destination.exists():
            destination.write_bytes(
                normalize_json_line_endings(source.read_bytes())
            )


def fetch_directory_file(year: int, source_path: str) -> None:
    destination = CACHE / f"moe_universities_{year}.xls"
    if destination.exists():
        return
    destination.write_bytes(download_bytes(directory_source_url(source_path)))
    if destination.stat().st_size < 100_000:
        raise ValueError(f"Downloaded institution file is implausibly small: {destination}")


def fetch_directory_api_fallback(year: int, source_path: str) -> None:
    destination = CACHE / f"moe_universities_{year}.xls"
    tree_url = (
        "https://api.github.com/repos/"
        f"{DATAXIV_REPOSITORY}/git/trees/{DATAXIV_COMMIT}"
    )
    payload = json.loads(download_bytes(tree_url).decode("utf-8"))
    matches = [
        item
        for item in payload.get("tree", [])
        if item.get("path") == source_path and item.get("type") == "blob"
    ]
    if not matches:
        raise FileNotFoundError(f"Pinned mirror path not found: {source_path}")
    blob_url = matches[0]["url"]
    blob_payload = json.loads(download_bytes(blob_url).decode("utf-8"))
    destination.write_bytes(base64.b64decode(blob_payload["content"]))


def refresh_directories() -> None:
    for year, source_path in DIRECTORY_PATHS.items():
        destination = CACHE / f"moe_universities_{year}.xls"
        if destination.exists():
            continue
        try:
            fetch_directory_file(year, source_path)
        except (OSError, URLError):
            fetch_directory_api_fallback(year, source_path)


def assert_vocational_cache_complete() -> None:
    missing = []
    for year in VOCATIONAL_YEARS:
        for slug in PROVINCE_SLUGS:
            path = VOCATIONAL / f"{year}_{slug}.json"
            if not path.exists():
                missing.append(path.name)
    if missing:
        raise FileNotFoundError(
            "Missing vocational source files: " + ", ".join(missing[:10])
        )


def write_manifest() -> None:
    normalize_vocational_cache()
    rows = []
    access_dates = previous_access_dates()
    default_accessed = date.today().isoformat()
    for year, mirror_path in DIRECTORY_PATHS.items():
        path = CACHE / f"moe_universities_{year}.xls"
        relative = str(path.relative_to(ROOT)).replace("\\", "/")
        rows.append(
            {
                "source_kind": "institution_directory",
                "year": year,
                "province_slug": "",
                "file_path": relative,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "source_url": directory_source_url(mirror_path),
                "official_page_url": OFFICIAL_PAGES.get(year, ""),
                "accessed_date": access_dates.get(relative, default_accessed),
            }
        )
    for year in VOCATIONAL_YEARS:
        for slug in PROVINCE_SLUGS:
            path = VOCATIONAL / f"{year}_{slug}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("data") is None:
                raise ValueError(f"Invalid vocational cache payload: {path}")
            relative = str(path.relative_to(ROOT)).replace("\\", "/")
            rows.append(
                {
                    "source_kind": "vocational_clinical_register",
                    "year": year,
                    "province_slug": slug,
                    "file_path": relative,
                    "sha256": sha256(path),
                    "bytes": path.stat().st_size,
                    "source_url": vocational_source_url(year, slug),
                    "official_page_url": "https://zwfw.moe.gov.cn/zyyxzy/",
                    "accessed_date": access_dates.get(relative, default_accessed),
                }
            )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def verify_manifest() -> int:
    if not MANIFEST.exists():
        raise FileNotFoundError(f"Source manifest is missing: {MANIFEST}")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != len(DIRECTORY_PATHS) + len(PROVINCE_SLUGS) * len(
        VOCATIONAL_YEARS
    ):
        raise ValueError("Source manifest has an unexpected number of rows.")
    seen = set()
    for row in rows:
        relative = row["file_path"]
        if relative in seen:
            raise ValueError(f"Duplicate source path in manifest: {relative}")
        seen.add(relative)
        path = ROOT / relative
        if not path.exists():
            raise FileNotFoundError(f"Manifest source is missing: {path}")
        if path.stat().st_size != int(row["bytes"]):
            raise ValueError(f"Source byte size changed: {path}")
        if sha256(path) != row["sha256"]:
            raise ValueError(f"Source hash changed: {path}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-legacy-cache",
        action="store_true",
        help="Copy existing output/raw/moe files into data/moe before verification.",
    )
    parser.add_argument(
        "--refresh-directories",
        action="store_true",
        help="Download any missing institution-list XLS from the pinned mirror.",
    )
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help="Regenerate the source manifest after changing the cache.",
    )
    args = parser.parse_args()

    if args.from_legacy_cache:
        ensure_cache_from_legacy()
    if args.refresh_directories:
        refresh_directories()
    assert_vocational_cache_complete()
    write_mode = (
        args.write_manifest or args.from_legacy_cache or args.refresh_directories
    )
    if write_mode:
        write_manifest()
        print(f"Wrote {MANIFEST}")
    else:
        count = verify_manifest()
        print(f"Verified {count} cached source files in {MANIFEST}")


if __name__ == "__main__":
    main()
