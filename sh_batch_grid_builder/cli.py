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


def parse_resolution(resolution_str: str) -> tuple[float, float]:
    """
    Parse resolution string in format (x,y) or x,y.
    
    Args:
        resolution_str: Resolution string like "(300,350)" or "300,350"
        
    Returns:
        Tuple of (resolution_x, resolution_y)
        
    Raises:
        ValueError: If the format is invalid
    """
    original_str = resolution_str
    # Remove whitespace
    resolution_str = resolution_str.strip()
    
    # Remove parentheses if present
    if resolution_str.startswith('(') and resolution_str.endswith(')'):
        resolution_str = resolution_str[1:-1].strip()
    
    # Split by comma
    parts = [p.strip() for p in resolution_str.split(',')]
    
    if len(parts) != 2:
        raise ValueError(
            f"Invalid resolution format: '{original_str}'. "
            f"Expected format: '(x,y)' or 'x,y' (e.g., '(300,350)' or '300,350')"
        )
    
    try:
        resolution_x = float(parts[0])
        resolution_y = float(parts[1])
        return resolution_x, resolution_y
    except ValueError as e:
        raise ValueError(
            f"Invalid resolution values: '{original_str}'. "
            f"Both values must be numbers (e.g., '(300,350)' or '300,350')"
        ) from e


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Generate bounding boxes or pixelated geometries from AOI files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate bounding box with same resolution for x and y
  sh-grid-builder input.geojson --resolution "(10,10)" --epsg 3035 --output-type bounding-box -o output.gpkg

  # Generate bounding box with different x and y resolutions
  sh-grid-builder input.geojson --resolution "(300,359)" --epsg 4326 --output-type bounding-box -o output.gpkg

  # Generate pixelated geometry (brackets optional)
  sh-grid-builder input.geojson --resolution "10,10" --epsg 3035 --output-type pixelated -o output.gpkg
        """
    )
    
    parser.add_argument(
        "input_aoi",
        type=str,
        help="Path to input AOI file (GeoJSON, GPKG, or other geospatial formats supported by GeoPandas)"
    )
    
    parser.add_argument(
        "--resolution",
        type=str,
        required=True,
        help="Grid resolution as (x,y) tuple in CRS coordinate units. "
             "Examples: '--resolution \"(300,359)\"' or '--resolution \"300,359\"' (quotes required). "
             "For projected CRS (e.g., EPSG:3035): resolution in meters (e.g., '(10,10)'). "
             "For geographic CRS (e.g., EPSG:4326): resolution in degrees (e.g., '(0.001,0.001)')."
    )
    
    parser.add_argument(
        "--epsg",
        type=int,
        required=True,
        help="EPSG code for the output CRS (e.g., 3035 for ETRS89 / LAEA Europe)"
    )
    
    parser.add_argument(
        "--output-type",
        type=str,
        choices=["bounding-box", "pixelated"],
        required=True,
        help="Type of output to generate: 'bounding-box' for aligned bounding boxes, 'pixelated' for pixelated geometry"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Path to output file (GPKG format required)"
    )
    
    parser.add_argument(
        "--strictly-within",
        action="store_true",
        help="For pixelated output: include only pixels whose full extent is strictly within the AOI. "
             "By default, all pixels that touch/intersect the AOI are included."
    )
    
    args = parser.parse_args()
    
    # Validate input file exists
    input_path = Path(args.input_aoi)
    if not input_path.exists():
        print(f"Error: Input file '{args.input_aoi}' does not exist.", file=sys.stderr)
        sys.exit(1)
    
    # Parse resolution string
    try:
        resolution_x, resolution_y = parse_resolution(args.resolution)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Validate resolutions
    if resolution_x <= 0:
        print(f"Error: Resolution X must be positive, got {resolution_x}", file=sys.stderr)
        sys.exit(1)
    if resolution_y <= 0:
        print(f"Error: Resolution Y must be positive, got {resolution_y}", file=sys.stderr)
        sys.exit(1)
    
    # Check CRS units and warn user
    try:
        crs_units = get_crs_units(args.epsg)
        print(f"CRS EPSG:{args.epsg} uses units: {crs_units}")
        print(f"Resolution X: {resolution_x} {crs_units}")
        print(f"Resolution Y: {resolution_y} {crs_units}")
        
        # Warn if using geographic CRS (degrees) with potentially inappropriate resolution
        if crs_units == "degrees":
            if resolution_x > 1.0 or resolution_y > 1.0:
                print(f"Warning: Resolution values greater than 1.0 degrees are very large. "
                      f"For EPSG:{args.epsg} (geographic CRS), resolution should be in degrees. "
                      f"Typical values are small (e.g., 0.001 degrees ≈ 111 meters).", file=sys.stderr)
            elif resolution_x < 0.00001 or resolution_y < 0.00001:
                print(f"Warning: Resolution values less than 0.00001 degrees are very small. "
                      f"This may result in extremely large pixel counts.", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Could not determine CRS units: {e}", file=sys.stderr)
        print("Proceeding with resolution as provided...", file=sys.stderr)
    
    try:
        # Initialize GeoData
        print(f"Loading AOI from: {args.input_aoi}")
        geo_data = GeoData(input_path, args.epsg, resolution_x, resolution_y)
        
        # Generate output based on type
        if args.output_type == "bounding-box":
            print(f"Generating aligned bounding box(es) with resolution X={resolution_x}, Y={resolution_y}...")
            result_gdf = geo_data.create_aligned_bounding_box(max_pixels=MAX_PIXELS)
            print(f"Created {len(result_gdf)} aligned bounding box(es)")
        else:  # pixelated
            all_touched = not args.strictly_within  # If strictly_within is True, all_touched is False
            pixel_mode = "strictly within" if args.strictly_within else "intersecting"
            print(f"Generating pixelated geometry with resolution X={resolution_x}, Y={resolution_y}...")
            print(f"Pixel inclusion mode: {pixel_mode}")
            result_gdf = geo_data.create_pixelated_geometry_split(max_pixels=MAX_PIXELS, all_touched=all_touched)
            print(f"Created {len(result_gdf)} pixelated geometry/geometries")
        
        # Save output
        output_path = Path(args.output)
        print(f"Saving output to: {output_path}")
        result_gdf.to_file(output_path, driver="GPKG")
        print(f"Successfully saved {len(result_gdf)} feature(s) to {output_path}")
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
