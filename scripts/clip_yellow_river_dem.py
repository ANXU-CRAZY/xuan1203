"""Create the project-extent DEM dataset from the complete Yellow River mosaic."""

import iobjectspy as sm

sm.set_gateway_port(59686)
source = sm.DatasourceConnectionInfo(
    server=r"D:\xuan1203-supermap\work\YellowRiverEcology3D\YellowRiverEcology3D.udbx",
    engine_type=sm.EngineType.UDBX,
)
datasource = sm.open_datasource(source)
output_name = "YellowRiver_DEM_GLO30_StudyArea"

if datasource.contains(output_name):
    output = datasource.get_dataset(output_name)
    print("CLIP_ALREADY_EXISTS", output.bounds)
else:
    input_grid = datasource.get_dataset("YellowRiver_DEM_GLO30")
    boundary = sm.GeoRegion([
        sm.Point2D(112.50, 34.20),
        sm.Point2D(115.10, 34.20),
        sm.Point2D(115.10, 35.90),
        sm.Point2D(112.50, 35.90),
    ])
    output = sm.clip_raster(
        input_grid,
        boundary,
        is_clip_in_region=True,
        is_exact_clip=False,
        out_data=datasource,
        out_dataset_name=output_name,
    )
    if not output:
        raise RuntimeError("DEM clipping failed")
    output.build_pyramid()
    datasource.flush()
    print("CLIP_CREATED", output.bounds, output.width, output.height, output.has_pyramid())

