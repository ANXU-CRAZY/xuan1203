"""Small DBF/Polygon(Z) readers shared by the protected-area converter."""
import struct
from pathlib import Path


def signed_area(ring):
    area = 0.0
    for index, point in enumerate(ring):
        next_point = ring[(index + 1) % len(ring)]
        area += point[0] * next_point[1] - next_point[0] * point[1]
    return area / 2.0

def point_in_ring(point, ring):
    x, y = point
    inside = False
    previous_x, previous_y = ring[-1]
    for current_x, current_y in ring:
        intersects = ((current_y > y) != (previous_y > y)) and (
            x < (previous_x - current_x) * (y - current_y) / ((previous_y - current_y) or 1e-12) + current_x
        )
        if intersects:
            inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside

def ensure_closed(ring):
    if ring and ring[0] != ring[-1]:
        return ring + [ring[0]]
    return ring

def normalize_ring_orientation(ring, outer=True):
    # GeoJSON convention: outer rings counter-clockwise, holes clockwise.
    area = signed_area(ring)
    if outer and area < 0:
        return list(reversed(ring))
    if not outer and area > 0:
        return list(reversed(ring))
    return ring

def rings_to_geometry(rings):
    if not rings:
        return {"type": "Polygon", "coordinates": []}

    closed = [ensure_closed(ring) for ring in rings if len(ring) >= 4]
    if not closed:
        return {"type": "Polygon", "coordinates": []}

    outers = []
    holes = []
    for ring in closed:
        # ESRI Shapefile usually stores outer rings clockwise and holes counter-clockwise.
        if signed_area(ring) < 0:
            outers.append({"ring": normalize_ring_orientation(ring, outer=True), "holes": []})
        else:
            holes.append(normalize_ring_orientation(ring, outer=False))

    if not outers:
        outers = [{"ring": normalize_ring_orientation(closed[0], outer=True), "holes": []}]
        holes = [normalize_ring_orientation(ring, outer=False) for ring in closed[1:]]

    for hole in holes:
        sample = hole[0]
        owner = next((outer for outer in outers if point_in_ring(sample, outer["ring"])), None)
        if owner:
            owner["holes"].append(hole)
        else:
            outers.append({"ring": normalize_ring_orientation(hole, outer=True), "holes": []})

    polygons = [[outer["ring"], *outer["holes"]] for outer in outers]
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}

def read_dbf(dbf_path: Path):
    raw = dbf_path.read_bytes()
    record_count = struct.unpack("<I", raw[4:8])[0]
    header_len = struct.unpack("<H", raw[8:10])[0]
    record_len = struct.unpack("<H", raw[10:12])[0]

    fields = []
    offset = 32
    while offset < header_len - 1:
        descriptor = raw[offset:offset + 32]
        if descriptor[0] == 0x0D:
            break
        name = descriptor[:11].split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        field_type = chr(descriptor[11])
        field_len = descriptor[16]
        fields.append((name, field_type, field_len))
        offset += 32

    records = []
    for record_index in range(record_count):
        start = header_len + record_index * record_len
        record = raw[start:start + record_len]
        if not record or record[0:1] == b"*":
            records.append({})
            continue

        values = {}
        field_offset = 1
        for name, field_type, field_len in fields:
            raw_value = record[field_offset:field_offset + field_len]
            value = raw_value.decode("utf-8", "replace").strip()
            if field_type == "N" and value.endswith(".00000000000"):
                value = value.split(".", 1)[0]
            values[name] = value
            field_offset += field_len
        records.append(values)

    return records

def read_shp_polygons(shp_path: Path):
    geometries = []
    with shp_path.open("rb") as shp_file:
        header = shp_file.read(100)
        if len(header) != 100:
            raise ValueError(f"Invalid Shapefile header: {shp_path}")
        shape_type = struct.unpack("<i", header[32:36])[0]
        if shape_type not in (5, 15):
            raise ValueError(f"Only Polygon Shapefiles are supported, got shape type {shape_type}")

        while True:
            record_header = shp_file.read(8)
            if not record_header:
                break
            if len(record_header) != 8:
                raise ValueError("Corrupted Shapefile record header")

            content_len = struct.unpack(">i", record_header[4:8])[0] * 2
            content = shp_file.read(content_len)
            if len(content) != content_len:
                raise ValueError("Corrupted Shapefile record body")

            record_shape_type = struct.unpack("<i", content[0:4])[0]
            if record_shape_type == 0:
                geometries.append({"type": "Polygon", "coordinates": []})
                continue
            if record_shape_type not in (5, 15):
                raise ValueError(f"Unsupported record shape type {record_shape_type}")

            num_parts = struct.unpack("<i", content[36:40])[0]
            num_points = struct.unpack("<i", content[40:44])[0]
            parts_offset = 44
            points_offset = parts_offset + 4 * num_parts
            parts = list(struct.unpack(f"<{num_parts}i", content[parts_offset:points_offset]))
            points = [
                struct.unpack("<2d", content[points_offset + index * 16:points_offset + (index + 1) * 16])
                for index in range(num_points)
            ]

            rings = []
            for index, start in enumerate(parts):
                end = parts[index + 1] if index + 1 < len(parts) else num_points
                rings.append(points[start:end])
            geometries.append(rings_to_geometry(rings))

    return geometries
