"""Import all downloaded DEM tiles and build a SuperMap raster mosaic."""

import glob
import os

import iobjectspy as sm


GATEWAY_PORT = 59686
WORK_DIR = r"D:\xuan1203-supermap\work\YellowRiverEcology3D"
WORKSPACE_PATH = os.path.join(WORK_DIR, "YellowRiverEcology3D.smwu")
DATASOURCE_PATH = os.path.join(WORK_DIR, "YellowRiverEcology3D.udbx")
DEM_DIR = r"F:\supermap\02-Data\YellowRiverEcology_DEM_GLO30"


def main():
    sm.set_gateway_port(GATEWAY_PORT)
    workspace_info = sm.WorkspaceConnectionInfo(
        server=WORKSPACE_PATH, workspace_type=sm.WorkspaceType.SMWU
    )
    workspace = sm.Workspace()
    if not workspace.open(workspace_info):
        raise RuntimeError("Unable to open generated DEM workspace")

    datasource_info = sm.DatasourceConnectionInfo(
        server=DATASOURCE_PATH,
        engine_type=sm.EngineType.UDBX,
        alias="YellowRiverEcology3D",
    )
    datasource = sm.open_datasource(datasource_info)
    if datasource is None:
        raise RuntimeError("Unable to open generated DEM datasource")

    existing = {dataset.name for dataset in datasource.datasets}
    tif_files = sorted(glob.glob(os.path.join(DEM_DIR, "*.tif")))
    for index, tif_path in enumerate(tif_files, start=1):
        dataset_name = "DEM_N{0}_E{1}".format(
            os.path.basename(tif_path).split("_N", 1)[1].split("_00", 1)[0],
            os.path.basename(tif_path).split("_E", 1)[1].split("_00", 1)[0],
        )
        if dataset_name in existing:
            print("SKIP", dataset_name)
            continue
        result = sm.import_tif(
            tif_path,
            datasource,
            out_dataset_name=dataset_name,
            is_import_as_grid=True,
            is_build_pyramid=True,
        )
        if not result:
            raise RuntimeError("Failed to import " + tif_path)
        print("IMPORTED", index, dataset_name)

    datasets = [datasource.get_dataset(name) for name in sorted(existing | {
        d.name for d in datasource.datasets
    })]
    datasets = [dataset for dataset in datasets if dataset is not None]
    if len(datasets) < 8:
        raise RuntimeError("Expected 8 DEM datasets, found %d" % len(datasets))

    mosaic_name = "YellowRiver_DEM_GLO30"
    if not datasource.contains(mosaic_name):
        mosaic = sm.raster_mosaic(
            datasets,
            back_or_no_value=0,
            back_tolerance=0,
            join_method=sm.RasterJoinType.RJMFIRST,
            join_pixel_format=sm.RasterJoinPixelFormat.RJPFLOAT,
            cell_size=datasets[0].bounds.width / datasets[0].width,
            out_data=datasource,
            out_dataset_name=mosaic_name,
        )
        if not mosaic:
            raise RuntimeError("Failed to mosaic DEM datasets")
        print("MOSAIC_CREATED", mosaic_name)
    else:
        print("MOSAIC_EXISTS", mosaic_name)

    datasource.flush()
    workspace.save()
    print("WORKSPACE_READY", WORKSPACE_PATH)
    print("DATASOURCE_READY", DATASOURCE_PATH)


if __name__ == "__main__":
    main()

