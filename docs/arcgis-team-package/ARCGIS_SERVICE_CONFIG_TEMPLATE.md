# ArcGIS Service Configuration Record

Complete this file in your private project notes after the database import and
before connecting the web page to a live ArcGIS service. Do not put passwords,
tokens, or API keys in this file if it will be committed or shared.

| Item | Value to record |
| --- | --- |
| Developer | |
| Date | |
| ArcGIS Pro version | |
| ArcGIS Server version | |
| Portal URL (if used) | |
| Server REST root | |
| Publishing connection file location | local path only, do not commit |
| Published item / service name | |
| Feature Service REST URL | |
| Map Service REST URL | |
| Geometry service URL | |
| Spatial reference | EPSG:4326 input; service output: |
| Database views published | |
| Service account privileges verified | yes/no |
| Browser CORS origin(s) allowed | |
| Test URL and date | |

## Required Pre-Publish Checks

- The published source is a read-only database view or materialized view.
- The service account has only the permissions it needs.
- A browser can read the service without exposing an administrator account.
- Query, extent, and renderer behavior were tested with the actual WGS 84 data.
- The current service REST URL works in a private/incognito browser session as
  intended by the deployment access policy.
