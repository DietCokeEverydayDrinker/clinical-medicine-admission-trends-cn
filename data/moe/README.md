# Ministry of Education source cache

This directory contains the official-source snapshot used to reconstruct
institution and programme eligibility for the clinical-medicine admission
panel.

## Institution lists

`moe_universities_YYYY.xls` are annual ordinary higher-education institution
lists published by the Ministry of Education. The files are pinned to commit
`96abde9ea3b412ce643fbeb79f686ae65bd7e61f` in
`dataxiv/data-universities`, a public mirror of the ministry XLS files.

The 2017 and 2026 files were additionally checked against the ministry's
own published pages. The exact URLs and SHA-256 hashes for every cached file
are recorded in `moe_source_manifest.csv`.

## Vocational clinical-programme registrations

`vocational_clinical/YYYY_XX.json` are responses from the ministry's
Higher Vocational Education Major Registration Query:

<https://zwfw.moe.gov.cn/zyyxzy/>

The cache contains queries for 2017-2026 and 32 provincial-level
jurisdictions, including Xinjiang Production and Construction Corps. Each
query uses `majorName=临床医学`; pagination and source URLs are represented in
the manifest.

The portal intermittently rejects scripted requests even when the same query
works in a browser. The committed JSON responses therefore serve both as the
reproducible source snapshot and as a fallback for that instability.

## Rebuild

Run:

```powershell
.\.venv-analysis\Scripts\python.exe scripts\fetch_moe_sources.py
```

By default, this verifies that every file matches the committed source
manifest. Use `--refresh-directories` to download missing institution-list
files from the pinned mirror. `--write-manifest` records a new cache snapshot.
