$ErrorActionPreference = 'Stop'

$outputDir = 'F:\supermap\02-Data\YellowRiverEcology_DEM_GLO30'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

# Covers Zhengzhou, Jiaozuo, and Xinxiang: 112.50-115.10E, 34.20-35.90N.
$tiles = foreach ($lat in 34, 35) {
    foreach ($lon in 112, 113, 114, 115) {
        [pscustomobject]@{ Latitude = $lat; Longitude = $lon }
    }
}

foreach ($tile in $tiles) {
    $lat = 'N{0:D2}' -f $tile.Latitude
    $lon = 'E{0:D3}' -f $tile.Longitude
    $name = "Copernicus_DSM_COG_10_${lat}_00_${lon}_00_DEM"
    $destination = Join-Path $outputDir "$name.tif"
    if (Test-Path $destination) {
        Write-Host "Exists: $name"
        continue
    }
    $url = "https://copernicus-dem-30m.s3.amazonaws.com/$name/$name.tif"
    Write-Host "Downloading: $name"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $destination
}

@"
Dataset: Copernicus DEM GLO-30 (DSM, approximately 30 m)
Source: https://copernicus-dem-30m.s3.amazonaws.com/
Downloaded tiles: N34/N35, E112/E113/E114/E115
Target extent: 112.50-115.10E, 34.20-35.90N
Next: Mosaic and clip in SuperMap iDesktopX using the project boundary, then build terrain pyramids/cache before publishing a 3D service.
"@ | Set-Content -Encoding utf8 (Join-Path $outputDir 'README.txt')
