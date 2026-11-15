# Data provenance

Every record keeps: source, accession or event id, title, measurement details, units (only if stated in the file header or metadata), original source URL, retrieval time and processing status.
Records are stored in the `nasa_records` table (SQLite) and, for processed files, as JSON sidecars in `data/nasa/metadata/`.

| Label | Meaning |
|---|---|
| NASA_OBSERVED | Measurement or event published by NASA (DONKI events, NASA images) |
| NASA_RESEARCH | Published NASA research data or metadata (OSDR, NTRS, Human Research Roadmap) |
| NASA_DERIVED | Computed here from NASA data, with the method recorded |
| EXTERNAL_RESEARCH | Outside NASA repositories (for example a GEO id referenced by an OSDR study) |
| SIMULATED_DEMO | Produced by the demo simulator. Not real astronaut telemetry |
| UNAVAILABLE | Could not be retrieved, with the reason. Nothing is invented in its place |

Folders: `data/nasa/raw/<accession>/` (original files, untouched), `data/nasa/processed/<accession>/` (cleaned CSV), `data/nasa/metadata/` (sidecars), `data/nasa/cache/` (HTTP cache).
Downloads are limited to files listed by NASA for that accession, to `*.nasa.gov` hosts, and to `NASA_MAX_DOWNLOAD_MB` (default 25 MB, size checked before download).
