"""
Example script for using SH Batch Grid Builder.

Note: For command-line usage, use the 'sh-grid-builder' CLI tool instead.
"""

from sh_batch_grid_builder.geo import GeoData
from sh_batch_grid_builder.crs import get_crs_data


def main():

    INPUT_GEOJSON = "data/Swiss_test.geojson"
    OUTPUT_ALIGNED = "data/aligned_bbox.gpkg"
    OUTPUT_PIXELATED = "data/pixelated.gpkg"

    RESOLUTION_X = 10
    RESOLUTION_Y = 10
    EPSG = 3035

    # Open the input GeoJSON file
    geo_data = GeoData(INPUT_GEOJSON, EPSG, RESOLUTION_X, RESOLUTION_Y)

    # Get the CRS data
    origin_x, origin_y = get_crs_data(EPSG)
    print(f"CRS origin: ({origin_x}, {origin_y})")

    # Create aligned bbox with automatic splitting if exceeds 3500px limit
    aligned_bbox = geo_data.create_aligned_bounding_box(max_pixels=3500)
    print(f"Created {len(aligned_bbox)} aligned bounding box(es)")
    aligned_bbox.to_file(OUTPUT_ALIGNED, driver="GPKG")

    # Create pixelated geometry with automatic splitting if exceeds 3500px limit
    pixelated_geometry = geo_data.create_pixelated_geometry_split(max_pixels=3500)
    print(f"Created {len(pixelated_geometry)} pixelated geometry/geometries")
    pixelated_geometry.to_file(OUTPUT_PIXELATED, driver="GPKG")


if __name__ == "__main__":
    main()
