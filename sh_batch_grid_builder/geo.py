from pathlib import Path
from typing import Union
import math
import numpy as np
import geopandas as gpd
from shapely.geometry import box, shape, Polygon, MultiPolygon
from shapely.ops import unary_union
from sh_batch_grid_builder.crs import get_crs_data
from pyproj import CRS
from rasterio import features
from rasterio.transform import from_origin


class GeoData:
    """
    A class for working with geodata and creating aligned bounding boxes to the projection grid.

    Args:
        filepath: Path to the input geodata file
        epsg_code: EPSG code of the input geodata
        resolution_x: Resolution of the input geodata in x direction
        resolution_y: Resolution of the input geodata in y direction
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        epsg_code: int,
        resolution_x: float,
        resolution_y: float,
    ):
        self.gdf = self.read_geodata(filepath)
        self.crs = epsg_code
        self.bounds = self.gdf.total_bounds

        self.resolution_x = resolution_x
        self.resolution_y = resolution_y
        self._validate_resolutions()

        self._validate_epsg(epsg_code)
        self.epsg_code = epsg_code

    def _validate_resolutions(self):
        if self.resolution_x <= 0:
            raise ValueError(f"Resolution X must be positive, got {self.resolution_x}")
        if self.resolution_y <= 0:
            raise ValueError(f"Resolution Y must be positive, got {self.resolution_y}")

    def _validate_epsg(self, epsg_code: int):
        if self.gdf.crs.to_epsg() is None:
            raise ValueError(
                f"Could not determine EPSG code from input file CRS. "
                f"Expected EPSG:{epsg_code}. Please ensure the file has a valid EPSG CRS."
            )

        if self.gdf.crs.to_epsg() != epsg_code:
            raise ValueError(
                f"Input file CRS (EPSG:{self.gdf.crs.to_epsg()}) does not match target EPSG ({epsg_code}). "
                f"Please reproject the input file to EPSG:{epsg_code} before processing, "
                f"or use EPSG:{self.gdf.crs.to_epsg()} as the target EPSG."
            )

    def _align_axis(
        self, minv: float, maxv: float, origin: float, res: float
    ) -> tuple[float, float]:
        # Snap to grid defined by origin + k*res, with epsilon to avoid off-by-one.
        eps = res * 1e-9
        min_idx = math.floor((minv - origin) / res + eps)
        max_idx = math.ceil((maxv - origin) / res - eps)

        aligned_min = origin + min_idx * res
        aligned_max = origin + max_idx * res

        # Normalize length to an integer number of steps (guards floating error).
        steps = max(1, int(round((aligned_max - aligned_min) / res)))
        aligned_max = aligned_min + steps * res

        return aligned_min, aligned_max

    def _split_pixel_counts(self, total: int, parts: int) -> list[int]:
        base = total // parts
        remainder = total % parts
        return [base + 1 if i < remainder else base for i in range(parts)]

    @staticmethod
    def _remove_holes(geometry):
        if geometry.geom_type == "Polygon":
            return Polygon(geometry.exterior)
        if geometry.geom_type == "MultiPolygon":
            return MultiPolygon([Polygon(p.exterior) for p in geometry.geoms])
        return geometry

    def _grid_origin(self) -> tuple[float, float]:
        origin_x, origin_y = get_crs_data(self.crs)
        if not CRS.from_epsg(self.crs).is_projected:
            origin_x -= self.resolution_x / 2
            origin_y -= self.resolution_y / 2
        return origin_x, origin_y

    def read_geodata(self, filepath: Union[str, Path]):
        gdf = gpd.read_file(filepath)
        return gdf

    def create_aligned_bounding_box(self, max_pixels: int = 3500) -> gpd.GeoDataFrame:
        """
        Create an aligned bounding box to the projection grid that covers the input geometry.

        Args:
            max_pixels: Maximum allowed pixels in either dimension (default: 3500)

        Returns:
            GeoDataFrame with one or more bounding boxes (split if exceeds max_pixels)
        """
        # Get the grid origin from the CRS
        origin_x, origin_y = self._grid_origin()

        # Get the grid bounds of the input geometry
        minx, miny, maxx, maxy = self.bounds

        aligned_minx, aligned_maxx = self._align_axis(
            minx, maxx, origin_x, self.resolution_x
        )
        aligned_miny, aligned_maxy = self._align_axis(
            miny, maxy, origin_y, self.resolution_y
        )

        # Calculate width and height in pixels of the aligned bounding box
        width_px = int(round((aligned_maxx - aligned_minx) / self.resolution_x))
        height_px = int(round((aligned_maxy - aligned_miny) / self.resolution_y))

        # Snap max bounds to the pixel grid derived from the pixel counts.
        aligned_maxx = aligned_minx + width_px * self.resolution_x
        aligned_maxy = aligned_miny + height_px * self.resolution_y

        tiles_x = max(1, math.ceil(width_px / max_pixels))
        tiles_y = max(1, math.ceil(height_px / max_pixels))

        widths = self._split_pixel_counts(width_px, tiles_x)
        heights = self._split_pixel_counts(height_px, tiles_y)

        geometries = []
        y_min = aligned_miny
        for row_idx, tile_h in enumerate(heights, start=1):
            y_max = y_min + tile_h * self.resolution_y
            x_min = aligned_minx
            for col_idx, tile_w in enumerate(widths, start=1):
                x_max = x_min + tile_w * self.resolution_x
                geometries.append(
                    {
                        "geometry": box(x_min, y_min, x_max, y_max),
                        "width": tile_w,
                        "height": tile_h,
                        "row_idx": row_idx,
                        "col_idx": col_idx,
                    }
                )
                x_min = x_max
            y_min = y_max

        if not geometries:
            return gpd.GeoDataFrame(
                [],
                columns=["id", "identifier", "width", "height", "geometry"],
                crs=CRS.from_epsg(self.crs),
            )

        aoi_union = unary_union(self.gdf.geometry)
        filtered_tiles = [
            tile for tile in geometries if tile["geometry"].intersects(aoi_union)
        ]

        if not filtered_tiles:
            return gpd.GeoDataFrame(
                [],
                columns=["id", "identifier", "width", "height", "geometry"],
                crs=CRS.from_epsg(self.crs),
            )

        # Renumber tiles without gaps in row/col identifiers
        filtered_tiles.sort(key=lambda tile: (tile["row_idx"], tile["col_idx"]))
        renumbered_tiles = []
        current_row = None
        row_counter = 0
        col_counter = 0
        for tile in filtered_tiles:
            if tile["row_idx"] != current_row:
                row_counter += 1
                current_row = tile["row_idx"]
                col_counter = 0
            col_counter += 1
            renumbered_tiles.append(
                {
                    "geometry": tile["geometry"],
                    "width": tile["width"],
                    "height": tile["height"],
                    "identifier": f"tile_{col_counter}_{row_counter}",
                }
            )

        # Create GeoDataFrame and renumber sequentially
        bbox_gdf = gpd.GeoDataFrame(renumbered_tiles, crs=CRS.from_epsg(self.crs))
        bbox_gdf["id"] = range(1, len(bbox_gdf) + 1)

        # Reorder columns to match expected format
        bbox_gdf = bbox_gdf[["id", "identifier", "width", "height", "geometry"]]

        return bbox_gdf

    def create_pixelated_geometry(self, max_pixels: int = 3500) -> gpd.GeoDataFrame:
        """
        Rasterize AOI to aligned grid, then dissolve connected pixels into polygons.

        Args:
            max_pixels: Maximum allowed pixels in either dimension (default: 3500)

        Returns:
            GeoDataFrame of dissolved pixel groups.
        """
        # Get the grid origin from the CRS
        origin_x, origin_y = self._grid_origin()

        # Get the grid bounds of the input geometry
        minx, miny, maxx, maxy = self.bounds

        aligned_minx, aligned_maxx = self._align_axis(
            minx, maxx, origin_x, self.resolution_x
        )
        aligned_miny, aligned_maxy = self._align_axis(
            miny, maxy, origin_y, self.resolution_y
        )

        # Calculate width and height in pixels of the aligned bounding box
        width_px = int(round((aligned_maxx - aligned_minx) / self.resolution_x))
        height_px = int(round((aligned_maxy - aligned_miny) / self.resolution_y))

        if width_px <= 0 or height_px <= 0:
            return gpd.GeoDataFrame([], crs=self.gdf.crs)

        # Snap max bounds to the pixel grid derived from the pixel counts.
        aligned_maxx = aligned_minx + width_px * self.resolution_x
        aligned_maxy = aligned_miny + height_px * self.resolution_y

        transform = from_origin(
            aligned_minx, aligned_maxy, self.resolution_x, self.resolution_y
        )

        shapes = ((geom, 1) for geom in self.gdf.geometry)
        mask = features.rasterize(
            shapes=shapes,
            out_shape=(height_px, width_px),
            transform=transform,
            fill=0,
            all_touched=True,
            dtype="uint8",
        )

        tiles_x = max(1, math.ceil(width_px / max_pixels))
        tiles_y = max(1, math.ceil(height_px / max_pixels))

        widths = self._split_pixel_counts(width_px, tiles_x)
        heights = self._split_pixel_counts(height_px, tiles_y)

        split_polygons = []
        y_offset = 0
        for row_idx, tile_h in enumerate(heights, start=1):
            x_offset = 0
            for col_idx, tile_w in enumerate(widths, start=1):
                window = mask[
                    y_offset : y_offset + tile_h,
                    x_offset : x_offset + tile_w,
                ]
                if window.any():
                    active = window > 0
                    ys, xs = np.where(active)
                    active_w = int(xs.max() - xs.min() + 1)
                    active_h = int(ys.max() - ys.min() + 1)

                    tile_identifier = f"tile_{col_idx}_{row_idx}"
                    window_transform = from_origin(
                        aligned_minx + x_offset * self.resolution_x,
                        aligned_maxy - y_offset * self.resolution_y,
                        self.resolution_x,
                        self.resolution_y,
                    )
                    feature_idx = 0
                    for geom, value in features.shapes(
                        window, mask=active, transform=window_transform
                    ):
                        feature_idx += 1
                        split_polygons.append(
                            {
                                "geometry": self._remove_holes(shape(geom)),
                                "width": active_w,
                                "height": active_h,
                                "identifier": f"{tile_identifier}_{feature_idx}",
                            }
                        )
                x_offset += tile_w
            y_offset += tile_h

        if not split_polygons:
            return gpd.GeoDataFrame([], crs=self.gdf.crs)

        pixel_gdf = gpd.GeoDataFrame(split_polygons, crs=self.gdf.crs)
        pixel_gdf["id"] = range(1, len(pixel_gdf) + 1)
        pixel_gdf = pixel_gdf[["id", "identifier", "width", "height", "geometry"]]
        return pixel_gdf
