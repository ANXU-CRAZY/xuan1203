"""Import the Yellow River main channel into the existing 3D UDBX datasource."""

from pathlib import Path

import iobjectspy as sm


WORK_DIR = Path(r"D:\xuan1203-supermap\work\YellowRiverEcology3D")
DATA_SOURCE = WORK_DIR / "YellowRiverEcology3D.udbx"
SOURCE_FILE = WORK_DIR / "YellowRiver_MainChannel.geojson"
# GeoJSON line imports are stored by iDesktopX with the ``_L`` geometry suffix.
DATASET_NAME = "YellowRiver_MainChannel_L"


def main():
    sm.set_gateway_port(59686)
    connection = sm.DatasourceConnectionInfo(
        server=str(DATA_SOURCE), engine_type=sm.EngineType.UDBX, alias="YellowRiverEcology3D"
    )
    datasource = sm.open_datasource(connection)
    if datasource is None:
        raise RuntimeError("Unable to open the 3D UDBX datasource")

    result = sm.import_geojson(
        str(SOURCE_FILE),
        datasource,
        out_dataset_name="YellowRiver_MainChannel",
        import_mode=sm.ImportMode.OVERWRITE,
        source_file_charset="UTF-8",
    )
    if not result:
        raise RuntimeError("GeoJSON import failed")

    dataset = datasource.get_dataset(DATASET_NAME)
    if dataset is None:
        raise RuntimeError("Imported dataset was not found")
    dataset.set_prj_coordsys(sm.PrjCoordSys.from_epsg_code(4326))
    datasource.set_prj_coordsys(sm.PrjCoordSys.from_epsg_code(4326))
    datasource.flush()
    print("DATASET", dataset.name)
    print("FEATURES", dataset.get_record_count())
    print("EPSG", dataset.prj_coordsys.to_epsg_code())
    print("BOUNDS", dataset.bounds.left, dataset.bounds.bottom, dataset.bounds.right, dataset.bounds.top)


if __name__ == "__main__":
    main()
