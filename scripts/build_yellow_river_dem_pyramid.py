"""Build pyramids for the generated Yellow River DEM mosaic."""

import iobjectspy as sm

sm.set_gateway_port(59686)
source = sm.DatasourceConnectionInfo(
    server=r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiverEcology3D.udbx",
    engine_type=sm.EngineType.UDBX,
)
datasource = sm.open_datasource(source)
dataset = datasource.get_dataset("YellowRiver_DEM_GLO30")
if dataset.has_pyramid():
    print("PYRAMID_ALREADY_EXISTS")
else:
    print("BUILDING_PYRAMID")
    dataset.build_pyramid()
    datasource.flush()
    print("PYRAMID_BUILD_FINISHED", dataset.has_pyramid())

