"""Render a lightweight, truthful preview from the downloaded Copernicus DEM tiles."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import tifffile


DEM_DIR = Path(r"F:\supermap\02-Data\YellowRiverEcology_DEM_GLO30")
OUT = Path(r"D:\xuan1203-supermap\work\YellowRiverEcology3D\yellow_river_dem_preview.png")

# Zhengzhou, Jiaozuo and Xinxiang project box.
WEST, SOUTH, EAST, NORTH = 112.50, 34.20, 115.10, 35.90
CELL = 1 / 3600


def read_window(lat, lon):
    path = DEM_DIR / f"Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif"
    # Copernicus COGs are compressed and tiled, so TIFF memory mapping is not
    # available. Load one source tile at a time for this lightweight preview.
    data = tifffile.imread(path)
    tile_west, tile_north = lon, lat + 1
    col0 = max(0, int(round((max(WEST, tile_west) - tile_west) / CELL)))
    col1 = min(data.shape[1], int(round((min(EAST, tile_west + 1) - tile_west) / CELL)))
    row0 = max(0, int(round((tile_north - min(NORTH, tile_north)) / CELL)))
    row1 = min(data.shape[0], int(round((tile_north - max(SOUTH, lat)) / CELL)))
    return np.asarray(data[row0:row1, col0:col1], dtype=np.float32)


def main():
    rows = []
    for lat in (35, 34):
        blocks = [read_window(lat, lon) for lon in (112, 113, 114, 115)]
        rows.append(np.hstack(blocks))
    dem = np.vstack(rows)
    # 30 m source data; show a 300 m screen-resolution preview.
    dem = dem[::10, ::10]
    dem[dem < -1000] = np.nan
    valid = dem[np.isfinite(dem)]
    vmin, vmax = np.percentile(valid, (2, 98))

    grad_y, grad_x = np.gradient(np.nan_to_num(dem, nan=np.nanmedian(valid)))
    slope = np.pi / 2 - np.arctan(np.hypot(grad_x, grad_y))
    aspect = np.arctan2(-grad_x, grad_y)
    azimuth, altitude = np.deg2rad(315), np.deg2rad(45)
    hillshade = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    hillshade = (hillshade - hillshade.min()) / (hillshade.max() - hillshade.min())

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), constrained_layout=True)
    extent = [WEST, EAST, SOUTH, NORTH]
    height = axes[0].imshow(dem, cmap="terrain", extent=extent, origin="upper", vmin=vmin, vmax=vmax)
    axes[0].set_title("Copernicus DEM GLO-30: elevation")
    axes[0].set_xlabel("Longitude (E)")
    axes[0].set_ylabel("Latitude (N)")
    fig.colorbar(height, ax=axes[0], label="Elevation (m)", shrink=0.8)

    axes[1].imshow(dem, cmap="terrain", extent=extent, origin="upper", vmin=vmin, vmax=vmax)
    axes[1].imshow(hillshade, cmap="gray", extent=extent, origin="upper", alpha=0.42)
    axes[1].set_title("Terrain preview: elevation with hillshade")
    axes[1].set_xlabel("Longitude (E)")
    axes[1].set_ylabel("Latitude (N)")
    for ax in axes:
        ax.scatter([113.62, 113.39, 114.90], [34.75, 35.22, 35.30], c=["#e84b43", "#20639b", "#f5a623"], s=34, edgecolors="white", linewidths=0.8)
    axes[1].text(113.62, 34.75, " Zhengzhou", color="white", fontsize=9, weight="bold")
    axes[1].text(113.39, 35.22, " Jiaozuo", color="white", fontsize=9, weight="bold")
    axes[1].text(114.90, 35.30, " Xinxiang", color="white", fontsize=9, weight="bold", ha="right")
    fig.suptitle("Yellow River ecology corridor DEM preview (112.50-115.10E, 34.20-35.90N)", fontsize=14, weight="bold")
    fig.savefig(OUT, dpi=180, facecolor="white")
    print(OUT)


if __name__ == "__main__":
    main()
