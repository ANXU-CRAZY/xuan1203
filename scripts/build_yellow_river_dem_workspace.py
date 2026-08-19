"""Build a separate SuperMap workspace for the Yellow River DEM terrain."""

import os
import sys

import iobjectspy as sm


GATEWAY_PORT = 59686
OUTPUT_DIR = r"D:\xuan1203-supermap\work\YellowRiverEcology3D"
WORKSPACE_PATH = os.path.join(OUTPUT_DIR, "YellowRiverEcology3D.smwu")
DATASOURCE_PATH = os.path.join(OUTPUT_DIR, "YellowRiverEcology3D.udbx")
DEM_DIR = r"F:\supermap\02-Data\YellowRiverEcology_DEM_GLO30"


def main():
    sm.set_gateway_port(GATEWAY_PORT)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if os.path.exists(DATASOURCE_PATH):
        raise RuntimeError("Target datasource already exists; refusing to overwrite it.")

    workspace_info = sm.WorkspaceConnectionInfo(
        server=WORKSPACE_PATH,
        workspace_type=sm.WorkspaceType.SMWU,
    )
    workspace = sm.Workspace()
    if os.path.exists(WORKSPACE_PATH):
        if not workspace.open(workspace_info):
            raise RuntimeError("Could not open the generated SuperMap workspace")
    else:
        if not workspace.create(workspace_info, save_existed=False):
            raise RuntimeError("Could not create SuperMap workspace")
        # iObjectSpy 2025 disposes the create handle after creation; reopen it
        # before creating datasources so the workspace owns the new datasource.
        workspace.close()
        workspace = sm.Workspace()
        if not workspace.open(workspace_info, save_existed=False):
            raise RuntimeError("Could not reopen SuperMap workspace")

    datasource_info = sm.DatasourceConnectionInfo(
        server=DATASOURCE_PATH,
        engine_type=sm.EngineType.UDBX,
        alias="YellowRiverEcology3D",
    )
    datasource = sm.create_datasource(datasource_info)
    if datasource is None:
        raise RuntimeError("Could not create UDBX datasource")

    first_tile = os.path.join(
        DEM_DIR, "Copernicus_DSM_COG_10_N34_00_E112_00_DEM.tif"
    )
    dataset = sm.import_tif(
        first_tile,
        datasource,
        out_dataset_name="DEM_N34_E112",
        is_import_as_grid=True,
        is_build_pyramid=True,
    )
    if dataset is None:
        raise RuntimeError("Could not import the DEM test tile")

    workspace.save()
    print("WORKSPACE_CREATED", WORKSPACE_PATH)
    print("DATASOURCE_CREATED", DATASOURCE_PATH)
    print("TEST_DATASET", dataset.name)


if __name__ == "__main__":
    main()

