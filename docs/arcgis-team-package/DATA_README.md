# Handoff Data Inventory

The package contains the raw/project data listed below. It intentionally
excludes the project owner's live PostgreSQL database, `.env.local`, private
`config/local_settings.py`, virtual environments, model weights, and media
uploads.

| File set | Purpose | Import status |
| --- | --- | --- |
| `bird_monitor_import_ready.csv` | Observation records, species, zones, dates, counts, coordinates | Import with `fast_import_observations` |
| `bird_monitor_missing_loc.csv` | Observation rows with missing location information | Reference only; do not import as spatial records without remediation |
| `species_meta_local.json` | Local species metadata | Reference only; no automatic import command |
| `zhuque_observations.xlsx` | Source/reference workbook | Reference only; no automatic import command |
| `水鸟监测点.*` | Monitoring point shapefile bundle | Import with `load_shp` |
| `水鸟监测样线.*` | Monitoring route shapefile bundle | Import with `load_shp` |

For a shapefile, every companion file must remain in the same folder. Never
move only the `.shp` file. The spatial files declare their coordinate system in
the `.prj`; check it in ArcGIS Pro before publishing.
