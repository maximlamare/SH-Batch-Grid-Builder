"""
Geometry pixelation module.

This module provides raster-based pixelation of geometries:
- Converts geometry to raster mask, then polygonizes back to vector
- Much faster than vector-based approaches for large grids
- Avoids creating thousands of individual polygons and expensive union operations
"""
from pathlib import Path
from typing import Union, Optional
import math
import re
import geopandas as gpd
from shapely.geometry import box, shape
from sh_batch_grid_builder.crs import get_crs_data
from pyproj import CRS


class GeoData:

    def __init__(self, filepath: Union[str, Path], epsg_code: int, resolution_x: float, resolution_y: float):
        self.gdf = self.read_geodata(filepath)
        self.crs = epsg_code
        
        # Validate resolutions
        if resolution_x <= 0:
            raise ValueError(f"Resolution X must be positive, got {resolution_x}")
        if resolution_y <= 0:
            raise ValueError(f"Resolution Y must be positive, got {resolution_y}")
        
        self.resolution_x = resolution_x
        self.resolution_y = resolution_y
        
        # Check if input file CRS matches target EPSG
        if self.gdf.crs is None:
            raise ValueError(
                f"Input file '{filepath}' has no CRS defined. "
                f"Please ensure the file has a CRS that matches EPSG:{epsg_code}."
            )
        
        # Get the EPSG code from the input file's CRS
        input_epsg = None
        if self.gdf.crs.to_epsg() is not None:
            input_epsg = self.gdf.crs.to_epsg()
        else:
            # Try to extract EPSG from CRS string if available
            crs_str = str(self.gdf.crs)
            if 'EPSG' in crs_str or 'epsg' in crs_str:
                # Try to parse EPSG code from CRS string
                match = re.search(r'epsg[:\s]*(\d+)', crs_str, re.IGNORECASE)
                if match:
                    input_epsg = int(match.group(1))
        
        if input_epsg is None:
            raise ValueError(
                f"Could not determine EPSG code from input file '{filepath}' CRS: {self.gdf.crs}. "
                f"Expected EPSG:{epsg_code}. Please ensure the file has a valid EPSG CRS."
            )
        
        if input_epsg != epsg_code:
            raise ValueError(
                f"Input file CRS (EPSG:{input_epsg}) does not match target EPSG ({epsg_code}). "
                f"Please reproject the input file to EPSG:{epsg_code} before processing, "
                f"or use EPSG:{input_epsg} as the target EPSG."
            )
        
        # Bounds are already in the correct CRS since we verified they match
        self.bounds = self.gdf.total_bounds

    def read_geodata(self, filepath: Union[str, Path]):
        gdf = gpd.read_file(filepath)
        return gdf

    def calculate_dimensions(self, resolution_x: Optional[float] = None, resolution_y: Optional[float] = None) -> tuple[int, int]:
        """
        Calculate pixel dimensions from bounds.
        
        Args:
            resolution_x: Optional X resolution (uses self.resolution_x if not provided)
            resolution_y: Optional Y resolution (uses self.resolution_y if not provided)
            
        Returns:
            Tuple of (width_pixels, height_pixels)
        """
        res_x = resolution_x if resolution_x is not None else self.resolution_x
        res_y = resolution_y if resolution_y is not None else self.resolution_y

        if res_x <= 0:
            raise ValueError(f"Resolution X must be positive, got {res_x}")
        if res_y <= 0:
            raise ValueError(f"Resolution Y must be positive, got {res_y}")

        minx, miny, maxx, maxy = self.bounds

        # Calculate dimensions in coordinate units
        width_coords = maxx - minx
        height_coords = maxy - miny

        # Convert to pixels and round up to ensure full coverage
        width_pixels = math.ceil(width_coords / res_x)
        height_pixels = math.ceil(height_coords / res_y)

        return width_pixels, height_pixels

    def _check_bbox_pixel_size(
        self, minx: float, miny: float, maxx: float, maxy: float
    ) -> tuple[int, int]:
        """
        Calculate pixel dimensions from bbox coordinates.
        
        Args:
            minx, miny, maxx, maxy: Bounding box coordinates
            
        Returns:
            Tuple of (width_pixels, height_pixels)
        """
        width_coords = maxx - minx
        height_coords = maxy - miny
        
        width_pixels = math.ceil(width_coords / self.resolution_x)
        height_pixels = math.ceil(height_coords / self.resolution_y)
        
        return width_pixels, height_pixels

    def _split_bbox_aligned(
        self, minx: float, miny: float, maxx: float, maxy: float, max_pixels: int = 3500
    ) -> list[tuple[float, float, float, float]]:
        """
        Recursively split bounding box into smaller boxes that don't exceed pixel limit.
        Splits maintain grid alignment.
        
        Args:
            minx, miny, maxx, maxy: Bounding box coordinates
            max_pixels: Maximum allowed pixels in either dimension (default: 3500)
            
        Returns:
            List of (minx, miny, maxx, maxy) tuples for split bboxes
        """
        # Check if this bbox needs splitting
        width_pixels, height_pixels = self._check_bbox_pixel_size(minx, miny, maxx, maxy)
        
        if width_pixels <= max_pixels and height_pixels <= max_pixels:
            return [(minx, miny, maxx, maxy)]
        
        # Get the grid origin from the CRS
        origin_x, origin_y = get_crs_data(self.crs)
        
        # Determine split direction (split along larger dimension)
        split_horizontally = width_pixels > height_pixels
        
        if split_horizontally:
            # Split vertically (divide x dimension)
            # Calculate split point aligned to grid - always align to pixel edges (not centers)
            mid_x_coord = (minx + maxx) / 2
            
            # Offset by half resolution so pixel edges align with grid
            offset_x = self.resolution_x / 2.0
            mid_x_grid = (
                origin_x + round((mid_x_coord - origin_x + offset_x) / self.resolution_x) * self.resolution_x - offset_x
            )
            
            # Ensure we don't create zero-width boxes - must be at least one resolution away from edges
            if mid_x_grid <= minx:
                mid_x_aligned = minx + self.resolution_x
            elif mid_x_grid >= maxx:
                mid_x_aligned = maxx - self.resolution_x
            else:
                mid_x_aligned = mid_x_grid
            
            # Safety check: if we can't split further, return as-is (prevents infinite recursion)
            if mid_x_aligned <= minx or mid_x_aligned >= maxx:
                return [(minx, miny, maxx, maxy)]
            
            # Recursively split both halves
            left_boxes = self._split_bbox_aligned(minx, miny, mid_x_aligned, maxy, max_pixels)
            right_boxes = self._split_bbox_aligned(mid_x_aligned, miny, maxx, maxy, max_pixels)
            return left_boxes + right_boxes
        else:
            # Split horizontally (divide y dimension)
            # Calculate split point aligned to grid - always align to pixel edges (not centers)
            mid_y_coord = (miny + maxy) / 2
            
            # Offset by half resolution so pixel edges align with grid
            offset_y = self.resolution_y / 2.0
            mid_y_grid = (
                origin_y + round((mid_y_coord - origin_y + offset_y) / self.resolution_y) * self.resolution_y - offset_y
            )
            
            # Ensure we don't create zero-height boxes - must be at least one resolution away from edges
            if mid_y_grid <= miny:
                mid_y_aligned = miny + self.resolution_y
            elif mid_y_grid >= maxy:
                mid_y_aligned = maxy - self.resolution_y
            else:
                mid_y_aligned = mid_y_grid
            
            # Safety check: if we can't split further, return as-is (prevents infinite recursion)
            if mid_y_aligned <= miny or mid_y_aligned >= maxy:
                return [(minx, miny, maxx, maxy)]
            
            # Recursively split both halves
            bottom_boxes = self._split_bbox_aligned(minx, miny, maxx, mid_y_aligned, max_pixels)
            top_boxes = self._split_bbox_aligned(minx, mid_y_aligned, maxx, maxy, max_pixels)
            return bottom_boxes + top_boxes

    def _create_gdf_with_metadata(
        self,
        geometry,
        feature_id: int,
        identifier: str,
    ) -> gpd.GeoDataFrame:
        # Calculate width and height based on geometry extent and resolutions
        minx, miny, maxx, maxy = geometry.bounds
        width = int((maxx - minx) / self.resolution_x)
        height = int((maxy - miny) / self.resolution_y)

        return gpd.GeoDataFrame(
            {
                "id": [feature_id],
                "identifier": [identifier],
                "width": [width],
                "height": [height],
                "geometry": [geometry],
            },
            crs=CRS.from_epsg(self.crs),
        )

    def create_aligned_bounding_box(self, max_pixels: int = 3500) -> gpd.GeoDataFrame:
        """
        Create aligned bounding box, splitting if it exceeds pixel limit.
        
        Args:
            max_pixels: Maximum allowed pixels in either dimension (default: 3500)
            
        Returns:
            GeoDataFrame with one or more bounding boxes (split if needed)
        """
        # Get the grid origin from the CRS
        origin_x, origin_y = get_crs_data(self.crs)

        minx, miny, maxx, maxy = self.bounds

        # Snap bounds to grid - always align to pixel edges (not centers)
        # Offset by half resolution so pixel edges align with grid lines
        # This ensures pixels are aligned to edges for all CRS types
        offset_x = self.resolution_x / 2.0
        offset_y = self.resolution_y / 2.0
        
        aligned_minx = (
            origin_x + math.floor((minx - origin_x + offset_x) / self.resolution_x) * self.resolution_x - offset_x
        )
        aligned_miny = (
            origin_y + math.floor((miny - origin_y + offset_y) / self.resolution_y) * self.resolution_y - offset_y
        )
        aligned_maxx = (
            origin_x + math.ceil((maxx - origin_x + offset_x) / self.resolution_x) * self.resolution_x - offset_x
        )
        aligned_maxy = (
            origin_y + math.ceil((maxy - origin_y + offset_y) / self.resolution_y) * self.resolution_y - offset_y
        )

        # Split bbox if it exceeds pixel limit
        split_bboxes = self._split_bbox_aligned(
            aligned_minx, aligned_miny, aligned_maxx, aligned_maxy, max_pixels
        )
        
        # Get original geometry for intersection check
        if self.gdf.crs is None:
            gdf_for_check = self.gdf
        else:
            gdf_for_check = self.gdf.to_crs(epsg=self.crs)
        original_geom = gdf_for_check.unary_union
        
        # Filter bboxes that intersect with original geometry and create GeoDataFrame
        geometries = []
        for bbox_minx, bbox_miny, bbox_maxx, bbox_maxy in split_bboxes:
            # Calculate width and height based on bbox extent and resolutions
            width = int((bbox_maxx - bbox_minx) / self.resolution_x)
            height = int((bbox_maxy - bbox_miny) / self.resolution_y)
            
            # Recalculate bounds from width/height to ensure exact alignment with pixel grid
            # This ensures: bbox_maxx - bbox_minx == width * resolution_x exactly
            exact_maxx = bbox_minx + width * self.resolution_x
            exact_maxy = bbox_miny + height * self.resolution_y
            
            bbox_geom = box(bbox_minx, bbox_miny, exact_maxx, exact_maxy)
            # Check if bbox intersects with original geometry
            if bbox_geom.intersects(original_geom):
                geometries.append({
                    "geometry": bbox_geom,
                    "width": width,
                    "height": height,
                })
        
        if not geometries:
            raise ValueError("No aligned bounding boxes intersect with the original geometry")
        
        # Create GeoDataFrame and renumber sequentially
        result_gdf = gpd.GeoDataFrame(geometries, crs=CRS.from_epsg(self.crs))
        result_gdf['id'] = range(1, len(result_gdf) + 1)
        result_gdf['identifier'] = result_gdf['id'].astype(str)
        
        # Reorder columns to match expected format
        result_gdf = result_gdf[['id', 'identifier', 'width', 'height', 'geometry']]
        
        return result_gdf

    def create_pixelated_geometry(
        self, 
        bbox_bounds: Optional[tuple[float, float, float, float]] = None,
        all_touched: bool = True
    ) -> gpd.GeoDataFrame:
        """
        Creates pixelated geometry using raster-based approach.
        
        Converts geometry to raster mask, then polygonizes back to vector.
        This is much faster for large grids as it avoids creating thousands
        of individual polygons and expensive union operations.
        
        Args:
            bbox_bounds: Optional tuple (minx, miny, maxx, maxy) to clip geometry to specific bbox.
                        If None, uses self.bounds.
            all_touched: If True, include all pixels that touch/intersect the geometry (default).
                        If False, include only pixels whose full extent is strictly within the geometry.
                        Default: True
        
        Returns:
            GeoDataFrame with pixelated geometry
        """
        import numpy as np
        import rasterio
        from rasterio.features import rasterize, shapes
        from rasterio.transform import Affine
        from shapely.geometry import shape

        # Get the grid origin from the CRS
        origin_x, origin_y = get_crs_data(self.crs)

        # Use provided bbox_bounds or fall back to self.bounds
        if bbox_bounds is not None:
            minx, miny, maxx, maxy = bbox_bounds
        else:
            minx, miny, maxx, maxy = self.bounds

        # Snap bounds to grid (aligned bounds) - always align to pixel edges (not centers)
        # Offset by half resolution so pixel edges align with grid lines
        # This ensures pixels are aligned to edges for all CRS types
        offset_x = self.resolution_x / 2.0
        offset_y = self.resolution_y / 2.0
        
        aligned_minx = (
            origin_x + math.floor((minx - origin_x + offset_x) / self.resolution_x) * self.resolution_x - offset_x
        )
        aligned_miny = (
            origin_y + math.floor((miny - origin_y + offset_y) / self.resolution_y) * self.resolution_y - offset_y
        )
        aligned_maxx = (
            origin_x + math.ceil((maxx - origin_x + offset_x) / self.resolution_x) * self.resolution_x - offset_x
        )
        aligned_maxy = (
            origin_y + math.ceil((maxy - origin_y + offset_y) / self.resolution_y) * self.resolution_y - offset_y
        )

        # Calculate grid dimensions
        width = int((aligned_maxx - aligned_minx) / self.resolution_x)
        height = int((aligned_maxy - aligned_miny) / self.resolution_y)

        if width <= 0 or height <= 0:
            raise ValueError("Invalid grid dimensions")

        # Create transform explicitly to ensure pixel edges align correctly
        # The transform maps pixel coordinates (col, row) to geographic coordinates (x, y)
        # For rasters: row 0 is at the top (maximum y), row increases downward
        # Pixel (0, 0) maps to (aligned_minx, aligned_maxy) - top-left corner
        # We use negative resolution_y because raster rows increase downward (y decreases)
        # Affine parameters: (a, b, c, d, e, f) where:
        #   x = a*col + b*row + c
        #   y = d*col + e*row + f
        # So: a=resolution_x, b=0, c=aligned_minx, d=0, e=-resolution_y, f=aligned_maxy
        transform = Affine(
            self.resolution_x, 0, aligned_minx,
            0, -self.resolution_y, aligned_maxy
        )

        # Rasterize geometry - much faster than checking each cell
        # Use the unary union of all geometries, ensuring CRS compatibility
        if self.gdf.crs is None:
            gdf_to_rasterize = self.gdf
        else:
            # Ensure geometry is in the correct CRS
            gdf_to_rasterize = self.gdf.to_crs(epsg=self.crs)
        
        original_geom = gdf_to_rasterize.unary_union
        
        # Clip geometry to bbox if bbox_bounds provided
        if bbox_bounds is not None:
            bbox_polygon = box(minx, miny, maxx, maxy)
            original_geom = original_geom.intersection(bbox_polygon)
            # Handle empty geometry after clipping
            if original_geom.is_empty:
                raise ValueError("No geometry intersects with the provided bbox bounds")
        
        # Convert geometries to GeoJSON-like format for rasterization
        # Handle both single geometries and geometry collections
        geometries_for_rasterize = []
        
        if hasattr(original_geom, '__geo_interface__'):
            geom_dict = original_geom.__geo_interface__
            # Handle GeometryCollection
            if geom_dict['type'] == 'GeometryCollection':
                geometries_for_rasterize = [
                    geom for geom in geom_dict['geometries']
                    if geom['type'] in ['Polygon', 'MultiPolygon']
                ]
            else:
                geometries_for_rasterize = [geom_dict]
        else:
            # Fallback: use GeoDataFrame's __geo_interface__
            temp_gdf = gpd.GeoDataFrame([1], geometry=[original_geom], crs=gdf_to_rasterize.crs)
            geom_dict = temp_gdf.geometry.iloc[0].__geo_interface__
            if geom_dict['type'] == 'GeometryCollection':
                geometries_for_rasterize = [
                    geom for geom in geom_dict['geometries']
                    if geom['type'] in ['Polygon', 'MultiPolygon']
                ]
            else:
                geometries_for_rasterize = [geom_dict]

        if not geometries_for_rasterize:
            raise ValueError("No valid polygon geometries found for rasterization")

        # Rasterize: creates a binary mask where geometry exists
        # Always use all_touched=True first to get all intersecting pixels
        raster = rasterize(
            geometries_for_rasterize,
            out_shape=(height, width),
            transform=transform,
            fill=0,
            default_value=1,
            dtype=rasterio.uint8,
            all_touched=True,  # Get all pixels that touch the geometry
        )

        # If strictly_within mode, filter to only pixels fully contained in the AOI
        if not all_touched:
            # Use prepared geometry for much faster .within() checks
            from shapely.prepared import prep
            prepared_geom = prep(original_geom)
            
            pixel_polygons = []
            
            # Iterate through each pixel in the raster
            # Prepared geometry makes .within() checks 10-100x faster
            for row in range(height):
                for col in range(width):
                    if raster[row, col] > 0:
                        # Calculate the bounds of this pixel
                        # Transform pixel coordinates to geographic coordinates
                        x_min = aligned_minx + col * self.resolution_x
                        x_max = aligned_minx + (col + 1) * self.resolution_x
                        y_max = aligned_maxy - row * self.resolution_y
                        y_min = aligned_maxy - (row + 1) * self.resolution_y
                        
                        # Create pixel polygon
                        pixel_box = box(x_min, y_min, x_max, y_max)
                        
                        # Check if the entire pixel is within the original geometry
                        # Using prepared geometry makes this check much faster
                        if prepared_geom.contains(pixel_box):
                            pixel_polygons.append(pixel_box)
            
            if not pixel_polygons:
                raise ValueError("No grid cells are fully contained within the geometry")
            
            # Merge pixel polygons
            if len(pixel_polygons) == 1:
                pixelated_geom = pixel_polygons[0]
            else:
                from shapely.ops import unary_union
                pixelated_geom = unary_union(pixel_polygons)
            
            return self._create_gdf_with_metadata(pixelated_geom, 1, "1")

        # Default mode: polygonize all intersecting pixels
        # Polygonize: convert raster back to vector polygons
        # This automatically merges adjacent cells
        results = (
            {"properties": {"value": v}, "geometry": s}
            for i, (s, v) in enumerate(shapes(raster, transform=transform, mask=raster > 0))
        )

        # Convert to Shapely geometries and merge if multiple polygons
        polygons = []
        for result in results:
            geom = shape(result["geometry"])
            if geom.is_valid:
                polygons.append(geom)

        if not polygons:
            raise ValueError("No grid cells intersect with the geometry")

        # If multiple polygons, union them (but this is much faster than unioning thousands)
        if len(polygons) == 1:
            pixelated_geom = polygons[0]
        else:
            from shapely.ops import unary_union
            pixelated_geom = unary_union(polygons)

        return self._create_gdf_with_metadata(pixelated_geom, 1, "1")

    def create_pixelated_geometry_split(
        self, 
        max_pixels: int = 3500,
        all_touched: bool = True
    ) -> gpd.GeoDataFrame:
        """
        Create pixelated geometry with automatic splitting if bbox exceeds pixel limit.
        
        Creates pixelated geometry for each split bbox individually to avoid memory issues
        with large areas. This is more efficient than creating the full geometry first.
        
        Args:
            max_pixels: Maximum allowed pixels in either dimension (default: 3500)
            all_touched: If True, include all pixels that touch/intersect the geometry (default).
                        If False, include only pixels whose full extent is strictly within the geometry.
                        Default: True
            
        Returns:
            GeoDataFrame with one or more pixelated geometries (split if needed)
        """
        # Get split bboxes
        split_bboxes_gdf = self.create_aligned_bounding_box(max_pixels=max_pixels)
        
        # Create pixelated geometry for each split bbox individually
        all_geometries = []
        for idx, row in split_bboxes_gdf.iterrows():
            bbox_geom = row.geometry
            bbox_bounds = bbox_geom.bounds  # (minx, miny, maxx, maxy)
            
            try:
                # Create pixelated geometry for this split bbox
                # This clips the geometry during rasterization, avoiding edge artifacts
                pixelated_gdf = self.create_pixelated_geometry(bbox_bounds=bbox_bounds, all_touched=all_touched)
                pixelated_geom = pixelated_gdf.geometry.iloc[0]
                
                # Skip if geometry is empty
                if pixelated_geom.is_empty:
                    continue
                
                # Calculate width and height based on geometry extent and resolutions
                geom_minx, geom_miny, geom_maxx, geom_maxy = pixelated_geom.bounds
                width = int((geom_maxx - geom_minx) / self.resolution_x)
                height = int((geom_maxy - geom_miny) / self.resolution_y)
                
                # Add to results with metadata matching the split bbox
                all_geometries.append({
                    "id": row['id'],
                    "identifier": row['identifier'],
                    "width": width,
                    "height": height,
                    "geometry": pixelated_geom,
                })
            except ValueError as e:
                # Skip this bbox if no geometry intersects (already handled in create_pixelated_geometry)
                continue
        
        if not all_geometries:
            raise ValueError("No pixelated geometry could be generated for any split bbox")
        
        # Combine all results into single GeoDataFrame
        result_gdf = gpd.GeoDataFrame(all_geometries, crs=CRS.from_epsg(self.crs))
        
        return result_gdf
