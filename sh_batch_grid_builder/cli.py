#!/usr/bin/env python3
"""
Command-line interface for SH Batch Grid Builder.

This tool generates bounding boxes or pixelated geometries from AOI files.
"""
import argparse
import sys
from pathlib import Path
from sh_batch_grid_builder.geo import GeoData
from sh_batch_grid_builder.crs import get_crs_units

# Fixed maximum pixels setting - geometries will be automatically split if they exceed this limit
MAX_PIXELS = 3500


def _parse_resolution(value: str) -> tuple[float, float]:
    cleaned = value.strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = cleaned[1:-1].strip()
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    if len(parts) != 2:
        raise ValueError(
            "Resolution must be provided as '(x,y)' or 'x,y' with two values."
        )
    try:
        resolution_x = float(parts[0])
        resolution_y = float(parts[1])
    except ValueError as exc:
        raise ValueError("Resolution values must be numeric.") from exc
    if resolution_x <= 0 or resolution_y <= 0:
        raise ValueError(
            f"Resolution must be positive, got ({resolution_x}, {resolution_y})"
        )
    return resolution_x, resolution_y


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate bounding boxes or pixelated geometries from AOI files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate bounding box
  sh-grid-builder input.geojson --resolution "(10,10)" --epsg 3035 --output-type bounding-box -o output.gpkg

  # Generate pixelated geometry
  sh-grid-builder input.geojson --resolution "10,10" --epsg 3035 --output-type pixelated -o output.gpkg
        """,
    )

    parser.add_argument(
        "input_aoi",
        type=str,
        help="Path to input AOI file (GeoJSON, GPKG, or other geospatial formats supported by GeoPandas)",
    )

    parser.add_argument(
        "--resolution",
        type=str,
        required=True,
        help=(
            "Grid resolution as '(x,y)' or 'x,y' in CRS coordinate units "
            "(e.g., '(10,10)' for 10 meters, or '0.001,0.001' for degrees)"
        ),
    )

    parser.add_argument(
        "--epsg",
        type=int,
        required=True,
        help="EPSG code for the output CRS (e.g., 3035 for ETRS89 / LAEA Europe)",
    )

    parser.add_argument(
        "--output-type",
        type=str,
        choices=["bounding-box", "pixelated"],
        required=True,
        help="Type of output to generate: 'bounding-box' for aligned bounding boxes, 'pixelated' for pixelated geometry",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Path to output file (GPKG format required)",
    )

    args = parser.parse_args()

    # Validate input file exists
    input_path = Path(args.input_aoi)
    if not input_path.exists():
        print(f"Error: Input file '{args.input_aoi}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Parse and validate resolution
    try:
        resolution_x, resolution_y = _parse_resolution(args.resolution)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Check CRS units and warn user
    try:
        crs_units = get_crs_units(args.epsg)
        print(f"CRS EPSG:{args.epsg} uses units: {crs_units}")
        print(f"Resolution: ({resolution_x}, {resolution_y}) {crs_units}")

        # Warn if using geographic CRS (degrees) with potentially inappropriate resolution
        if crs_units == "degrees":
            if resolution_x > 1.0 or resolution_y > 1.0:
                print(
                    f"Warning: Resolution of ({resolution_x}, {resolution_y}) degrees is very large. "
                    f"For EPSG:{args.epsg} (geographic CRS), resolution should be in degrees. "
                    f"Typical values are small (e.g., 0.001 degrees ≈ 111 meters).",
                    file=sys.stderr,
                )
            elif resolution_x < 0.00001 or resolution_y < 0.00001:
                print(
                    f"Warning: Resolution of ({resolution_x}, {resolution_y}) degrees is very small. "
                    f"This may result in extremely large pixel counts.",
                    file=sys.stderr,
                )
    except Exception as e:
        print(f"Warning: Could not determine CRS units: {e}", file=sys.stderr)
        print("Proceeding with resolution as provided...", file=sys.stderr)

    try:
        # Initialize GeoData
        print(f"Loading AOI from: {args.input_aoi}")
        geo_data = GeoData(input_path, args.epsg, resolution_x, resolution_y)

        # Generate output based on type
        if args.output_type == "bounding-box":
            print(
                f"Generating aligned bounding box(es) with resolution ({resolution_x}, {resolution_y})..."
            )
            result_gdf = geo_data.create_aligned_bounding_box(max_pixels=MAX_PIXELS)
            print(f"Created {len(result_gdf)} aligned bounding box(es)")
        else:  # pixelated
            print(
                f"Generating pixelated geometry with resolution ({resolution_x}, {resolution_y})..."
            )
            result_gdf = geo_data.create_pixelated_geometry(max_pixels=MAX_PIXELS)
            print(f"Created {len(result_gdf)} pixelated geometry/geometries")

        # Save output
        output_path = Path(args.output)
        result_gdf.to_file(output_path, driver="GPKG")
        print(f"Successfully saved {len(result_gdf)} feature(s) to {output_path}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
