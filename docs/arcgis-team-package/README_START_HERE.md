# ArcGIS Team Package: Start Here

This folder is the portable handoff material for the ArcGIS developer. The
application source is obtained from GitHub; the data files are delivered in
the accompanying `data` folder or zip archive. Do not expect the project
author's database, virtual environment, passwords, media directory, ArcGIS
license, Portal account, or Server address to be included.

## 1. What You Need Before Starting

- Windows 10/11 recommended.
- Git.
- Python 3.11 or 3.12.
- PostgreSQL 15 or 16 with the PostGIS extension installed.
- ArcGIS Pro and/or access to ArcGIS Server or Portal, only when publishing
  services. The web project and PostGIS import can be completed first.

## 2. Download the Correct Code Branch

Open PowerShell in a workspace you control and run:

```powershell
git clone --branch competition/arcgis-server https://github.com/ANXU-CRAZY/xuan1203.git yellow-river-arcgis
cd yellow-river-arcgis
git status
```

`git status` must report the `competition/arcgis-server` branch. Do not clone
from a teammate's disk and do not copy their `.venv`, `anxu`, `.env.local`,
or `config/local_settings.py`.

## 3. Create Your Own Python Environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation for the current window, run
`Set-ExecutionPolicy -Scope Process Bypass` once, then activate again.

## 4. Create Your Own PostGIS Database

Use pgAdmin Query Tool or `psql` with an administrator account. Choose your
own password; it must never be committed, pasted in a ticket, or sent in this
package.

```sql
CREATE ROLE yellow_river_dev LOGIN PASSWORD 'choose-your-own-strong-password';
CREATE DATABASE yellow_river_arcgis OWNER yellow_river_dev;
\c yellow_river_arcgis
CREATE EXTENSION IF NOT EXISTS postgis;
```

In pgAdmin, the last two lines are instead performed by connecting Query Tool
to `yellow_river_arcgis` and executing `CREATE EXTENSION IF NOT EXISTS
postgis;`. Confirm with:

```sql
SELECT PostGIS_Full_Version();
```

## 5. Connect This Clone to Your Database

Copy the template:

```powershell
Copy-Item docs\arcgis-team-package\config\local_settings.example.py config\local_settings.py
notepad config\local_settings.py
```

Set `NAME`, `USER`, `PASSWORD`, `HOST`, and `PORT` to the values of your own
PostgreSQL instance. Keep `config/local_settings.py` private: Git ignores it.

## 6. Build the Schema and Local Account

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py check
```

If `check` reports that GDAL/GEOS/PROJ cannot be found, install a compatible
GIS runtime (for example OSGeo4W) and set its location as described in the
project's `config/settings.py`. This machine-level installation is not part
of the Git repository.

## 7. Import the Handoff Data

Copy the supplied `data` directory beside `manage.py`, then run these commands
from the repository root. The first command imports the observation CSV and
also creates its species and wetland-zone records. `--replace` is intentional
only for a newly created database.

```powershell
python manage.py fast_import_observations data\bird_monitor_import_ready.csv --replace
python manage.py load_shp
python manage.py normalize_protection_levels
python manage.py refresh_map_observation_cache --status all
python manage.py check
```

`load_shp` reads the Chinese-named monitoring point and route shapefiles from
the project's `data` directory. Keep every companion file (`.shp`, `.shx`,
`.dbf`, `.prj`, `.cpg`, and `.qmd`) together. The `species_meta_local.json`
and XLSX file are reference material; do not claim they have been imported
unless you implement and verify an importer for them.

## 8. Run and Verify the Web Application

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/` and verify:

- `/admin/` can be opened with the account created above.
- `http://127.0.0.1:8000/api/map-observations/?stats=1` returns JSON.
- `http://127.0.0.1:8000/api/map-observations/?bbox=110,34,111,35` responds
  without a server error. Adjust the bounding box to the imported data extent
  if it returns no records.

## 9. ArcGIS Work Begins Only After the Above Passes

Read `docs/ARCGIS_DEVELOPMENT_PLAYBOOK.md` in full. The agreed boundary is:

- Keep the existing Leaflet home page unchanged.
- Implement ArcGIS work on a separate `/arcgis/` page.
- Publish read-only PostGIS views or materialized views, never writable Django
  application tables.
- Source coordinates are WGS 84 / EPSG:4326. In ArcGIS JavaScript use
  `[longitude, latitude]`, not `[latitude, longitude]`.

Before publishing, record the service configuration in
`ARCGIS_SERVICE_CONFIG_TEMPLATE.md`. A real Server URL, Portal item ID,
credentials, license, and publishing permissions are organization-specific;
they cannot be generated from this code package.

## Database Snapshot Status

No PostgreSQL database dump is included in this package. Rebuild the database
with the CSV/SHP process above. This is deliberate: the original database and
its credentials stay on the project owner's machine. If a reviewed database
snapshot is later supplied, restore it only to a new database that you own;
do not overwrite an existing development database.
