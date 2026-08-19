"""Run inside the iDesktopX Python console to repair the active DEM scene."""

import iobjectspy as sm


# This script runs inside the iDesktopX Python console, where iObjectSpy has
# already initialized its own gateway. Do not set a fixed external port here.
workspace_path = r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiverEcology3D.smwu"
datasource_path = r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiverEcology3D.udbx"

workspace_info = sm.WorkspaceConnectionInfo(
    server=workspace_path, workspace_type=sm.WorkspaceType.SMWU
)
workspace = sm.Workspace()
workspace.open(workspace_info)
datasource = sm.open_datasource(
    sm.DatasourceConnectionInfo(
        server=datasource_path, engine_type=sm.EngineType.UDBX
    )
)
dataset = datasource.get_dataset("YellowRiver_DEM_GLO30_StudyArea")

print("DEM dataset:", dataset.name)
print("Bounds:", dataset.bounds)
print("Size:", dataset.width, dataset.height)
print("Pyramid:", dataset.has_pyramid())
print("CRS:", dataset.prj_coordsys.to_json())
print("Datasource:", datasource.connection_info.server)
print("Workspace:", workspace_path)
print("\nThe dataset is valid. In the active scene, remove the warning layer and add:")
print("YellowRiver_DEM_GLO30_StudyArea@YellowRiverEcology3D")
print("Then use Scene > Zoom to Layer and save the workspace.")
