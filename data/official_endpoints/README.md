# Official endpoint sources

This directory records the direct provincial-examination-authority files used
to reconstruct official 2025 and 2026 endpoint series. Raw files are not
committed because they total roughly 24 MB. Download them with:

```powershell
python scripts/fetch_official_endpoints.py --output-dir data/official_endpoints_cache
```

The fetcher verifies both file size and SHA-256. Parse the downloaded files
with:

```powershell
python scripts/parse_official_endpoints.py --input-dir data/official_endpoints_cache
```

The parser retains the full offer pool through percentile construction, writes
the clinical subset, and checks the sources against row counts already
reconciled for 2026.

Build the row-level reconciliation against the enriched panel with:

```powershell
python scripts/build_official_endpoint_reconciliation.py
```

This writes the 15 official-only or panel-only records to
`output/official_endpoints/official_endpoint_panel_reconciliation.csv` and
source-level counts to the adjacent JSON summary.
