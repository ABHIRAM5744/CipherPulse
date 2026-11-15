# NASA data sources: what was verified, and how

Verification date: 12 Nov 2026. "Fetched" means the response was read through a web-fetch tool during development.
The development sandbox could **not** resolve any `*.nasa.gov` host (DNS failure), so **no file was downloaded and no live DONKI call was made there**.
Run `validate_nasa.bat` (or `python scripts/validate_nasa.py`) on your own machine for the full end-to-end proof. It writes `data/nasa/validation_report.json`.

| Source | Endpoint used | Verified how | Status |
|---|---|---|---|
| OSDR catalogue | `visualization.osdr.nasa.gov/biodata/api/v2/datasets/` | Fetched. JSON object mapping accession to `REST_URL`. No titles in it | Shape verified |
| OSDR search | `osdr.nasa.gov/osdr/data/search?term=&from=&size=&type=cgene` | Fetched (`term=spaceflight` returned 395 matches). Elasticsearch format; fields `Accession`, `Study Title`, `organism`, `Material Type`, `Mission`, `Data Source Accession`, `Study Public Release Date` | Shape verified |
| OSDR dataset detail | `.../v2/dataset/OSD-483/` | Fetched. `{accession: {REST_URL, assays, files, metadata{lowercase keys}}}` | Shape verified |
| OSDR file listing | `.../v2/dataset/OSD-483/files/` | Fetched. `{accession: {files: {name: {REST_URL, URL}}}}` with real download URLs of the form `osdr.nasa.gov/geode-py/ws/studies/<acc>/download?source=datamanager&file=<name>` | Shape verified |
| OSDR file download | URL from the listing | A fetch attempt through the dev tool returned a client error. Cause not determined (tool or server) | **Unverified**. Code follows redirects, checks size first, reports errors |
| NASA Image Library search | `images-api.nasa.gov/search?q=&media_type=image` | Fetched. `collection.items[].data[0]` (`nasa_id`, `title`, `photographer`, `center`) and `links[]` with `~thumb`/`~orig` URLs | Shape verified |
| Image asset / metadata | `/asset/{id}`, `/metadata/{id}` | Documented endpoints, responses not fetched | Parsed defensively, unverified |
| DONKI | `api.nasa.gov/DONKI/{FLR,CME,SEP,GST,RBE,IPS,MPC,HSS,notifications}` with `startDate`, `endDate`, `api_key` | Endpoint list and parameters confirmed on the NASA CCMC DONKI documentation page. No live response fetched (needs an API key in the URL) | Endpoints documented, **response unverified live** |
| EDA | `visualization.osdr.nasa.gov/eda/` | Page fetched. Lists missions (RR, APEX, VEG), telemetry and radiation tables with downloads, and an API section. **The data endpoint is not visible in the page text** | **Endpoint not invented.** Set `EDA_API_BASE` after confirming it |
| NTRS | `ntrs.nasa.gov/api/citations/search?q=` | NTRS OpenAPI documentation located. Live response not fetched | Parsed defensively, unverified |
| Human Research Roadmap | `humanresearchroadmap.nasa.gov/risks/` | Page not fetched | Link scraping is a heuristic, unverified |

## Real human spaceflight studies seen in the OSDR search
OSD-483 (small RNA from plasma of 14 astronauts, *Homo sapiens*), OSD-903 and OSD-943 (Axiom-1 crew blood, RNA-seq and DNA methylation).
OSD-483's files are raw FASTQ plus an ISA-Tab metadata ZIP. FASTQ is a specialised sequencing format: it is listed and explained but not parsed as CSV.

## Accession rules
OSDR accessions look like `OSD-483`. GEO (`GSE...`), PRIDE (`PXD...`), MG-RAST and similar ids are different repositories. The code refuses them as OSDR accessions and shows them as `EXTERNAL_RESEARCH`.

## What is NOT available
- No public source of live astronaut vital signs exists. The live vitals in this app are `SIMULATED_DEMO`.
- DONKI records are solar and space-weather events. They are never shown as an astronaut's radiation dose.
- Most human OSDR studies are omics with small cohorts, not time series of heart rate or blood pressure.
