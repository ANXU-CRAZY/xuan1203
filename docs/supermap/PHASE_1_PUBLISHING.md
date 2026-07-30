# SuperMap iServer Phase 1

## Local prerequisites

- iServer catalog: `http://127.0.0.1:8090/iserver/services`
- SuperMap branch database: `YellowRiverSuperMap`
- Publishable spatial view: `supermap_observation_points`
- Coordinate reference system: `EPSG:4326`

Prepare the view after importing or refreshing observation data:

```powershell
D:\xuan1203\anxu\Scripts\python.exe manage.py prepare_supermap_layers
```

## Publish through iServer

1. Sign in at `http://127.0.0.1:8090/iserver/manager` with the existing iServer administrator account.
2. Create a PostGIS data source using the local `YellowRiverSuperMap` database. Do not store its credentials in this repository.
3. Add `supermap_observation_points` to a workspace. Its geometry field is `geom` and its coordinate system is `EPSG:4326`.
4. Publish a map service and a data service. Use `YellowRiverEcology` as the service name.
5. Put the public map-service endpoint in the local `SUPERMAP_MAP_SERVICE_URL` environment variable. The next phase will render that published layer on the main monitoring map.

The Django status endpoint is available at `/api/supermap/status/`, and the platform service page is `/supermap/`.
