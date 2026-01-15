# SH Batch Grid Builder

This tool is designed to build custom tiling grids for the [Sentinel Hub Batch V2 API](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/BatchV2.html) on [CDSE](https://dataspace.copernicus.eu/). The custom grid is built around an input AOI for a given projection and ensures the Batch request produces outputs matching the pixel grid of the given projection.

## Features

- **Aligned Bounding Boxes**: Generate projection grid-aligned bounding boxes that snap to a specified grid resolution
- **Pixelated Geometries**: Convert geometries to pixelated representations in order to only query data for the given AOI
- **Automatic Splitting**: Automatically splits large geometries that exceed pixel limits
- **Multiple CRS Support**: Works with any EPSG code, automatically handling CRS-specific grid origins

## Installation

### From PyPI

```bash
pip install sh-batch-grid-builder
```

### From Source

```bash
git clone https://github.com/maximlamare/SH-Batch-Grid-Builder.git
cd SH-Batch-Grid-Builder
pip install .
```

### Development Installation

```bash
git clone https://github.com/maximlamare/SH-Batch-Grid-Builder.git
cd SH-Batch-Grid-Builder
pip install -e ".[dev]"
```

## Usage

### Command Line Interface

The tool provides a command-line interface via the `sh-grid-builder` command:

```bash
sh-grid-builder <input_aoi> --resolution "(x,y)" --epsg <epsg_code> --output-type <type> -o <output_file>
```

#### Arguments

- `input_aoi`: Path to input AOI file (GeoJSON, GPKG, or other formats supported by GeoPandas)
- `--resolution`: Grid resolution as `(x,y)` tuple in CRS coordinate units:
  - Format: `"(x,y)"` or `"x,y"` (brackets optional, e.g., `"(300,359)"` or `"300,359"`)
  - **Important**: Always quote the resolution value to prevent shell interpretation (e.g., `--resolution "(300,359)"` or `--resolution "300,359"`)
  - Note the resolution **must** be in the units of the selected projection (e.g. EPSG:3035: resolution in meters; EPSG:4326: resolution in degrees).
  - X and Y resolutions can be different to support non-square pixels
- The tool automatically detects and displays the CRS units when running
- `--epsg`: EPSG code for the output CRS (e.g., `3035` for ETRS89 / LAEA Europe, `4326` for WGS84)
- `--output-type`: Type of output to generate:
  - `bounding-box`: Generate an aligned bounding box that covers the AOI
  - `pixelated`: Generate pixelated geometry of the AOI
- `-o, --output`: Path to output file (GPKG format required)

#### Examples

Generate aligned bounding boxes with same resolution for x and y:

```bash
sh-grid-builder data/aoi.geojson --resolution "(10,10)" --epsg 3035 --output-type bounding-box -o output_bbox.gpkg
```

Generate aligned bounding boxes with different x and y resolutions:

```bash
sh-grid-builder data/aoi.geojson --resolution "(300,359)" --epsg 32632 --output-type bounding-box -o output_bbox.gpkg
```

Generate pixelated geometry:

```bash
sh-grid-builder data/aoi.geojson --resolution "10,10" --epsg 3035 --output-type pixelated -o output_pixelated.gpkg
```

Example with geographic CRS (degrees):

```bash
sh-grid-builder data/aoi.geojson --resolution "(0.001,0.001)" --epsg 4326 --output-type bounding-box -o output_bbox.gpkg
```

### Python API

You can also use the package programmatically:

```python
from sh_batch_grid_builder import GeoData

# Initialize with AOI file, EPSG code, and resolutions (x, y)
geo_data = GeoData("path/to/aoi.geojson", epsg_code=3035, resolution_x=10.0, resolution_y=10.0)

# Or with different x and y resolutions
geo_data = GeoData("path/to/aoi.geojson", epsg_code=4326, resolution_x=0.002976190476204, resolution_y=0.002976190476204)

# Generate aligned bounding boxes
aligned_bboxes = geo_data.create_aligned_bounding_box(max_pixels=3500)

# Generate pixelated geometry (includes all pixels that touch/intersect the AOI)
pixelated_geom = geo_data.create_pixelated_geometry(max_pixels=3500)

# Save results
aligned_bboxes.to_file("output_bbox.gpkg", driver="GPKG")
pixelated_geom.to_file("output_pixelated.gpkg", driver="GPKG")
```

## How It Works

### Aligned Bounding Boxes

The tool creates bounding boxes that are aligned to a grid based on:
1. The specified X and Y resolutions (can be different for non-square pixels)
2. The CRS origin (false easting/northing) for projected coordinate systems
3. Automatic splitting when dimensions exceed 3500 pixels (fixed limit)

### Pixelated Geometries

The pixelated geometry generation uses a raster-based approach:
1. Converts the input geometry to a raster mask
2. Polygonizes the raster back to vector format
3. Automatically splits large geometries to avoid memory issues

This approach is much faster than vector-based methods for large grids. Pixelated
output includes any pixel that touches/intersects the AOI.

## Requirements

- Python >= 3.8
- geopandas >= 0.12.0
- pyproj >= 3.4.0
- shapely >= 2.0.0
- rasterio >= 1.3.0
- numpy >= 1.21.0

## Development

### Running Tests

```bash
pytest
```

### Building the Package

```bash
python -m build
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
