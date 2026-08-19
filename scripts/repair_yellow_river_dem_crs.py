"""Explicitly assign WGS 84 to generated DEM datasets and refresh pyramids."""

import iobjectspy as sm

sm.set_gateway_port(59686)
source = sm.DatasourceConnectionInfo(
    server=r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiverEcology3D.udbx",
    engine_type=sm.EngineType.UDBX,
)
datasource = sm.open_datasource(source)
wgs84 = sm.PrjCoordSys.from_epsg_code(4326)

for name in ("YellowRiver_DEM_GLO30", "YellowRiver_DEM_GLO30_StudyArea"):
    dataset = datasource.get_dataset(name)
    dataset.set_prj_coordsys(wgs84)
    if not dataset.has_pyramid():
        dataset.build_pyramid()
    print(name, dataset.prj_coordsys.to_epsg_code(), dataset.has_pyramid())

datasource.set_prj_coordsys(wgs84)
datasource.flush()
print("DEM_CRS_REPAIRED")
