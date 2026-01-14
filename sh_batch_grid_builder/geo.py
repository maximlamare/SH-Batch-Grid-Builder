from pathlib import Path
from typing import Union
import math
import geopandas as gpd
from shapely.geometry import box
from sh_batch_grid_builder.crs import get_crs_data
from pyproj import CRS


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
        # snap to grid defined by origin + k*res
        aligned_min = origin + math.floor((minv - origin) / res) * res
        aligned_max = origin + math.ceil((maxv - origin) / res) * res

        # ensure width/height is multiple of res (guards floating error)
        size = aligned_max - aligned_min
        steps = math.ceil(size / res)
        aligned_max = aligned_min + steps * res

        return aligned_min, aligned_max

    def _split_pixel_counts(self, total: int, parts: int) -> list[int]:
        base = total // parts
        remainder = total % parts
        return [base + 1 if i < remainder else base for i in range(parts)]

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
        origin_x, origin_y = get_crs_data(self.crs)

        # Convert to edge of pixel and not the center
        origin_x -= self.resolution_x / 2
        origin_y -= self.resolution_y / 2

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

        if width_px <= max_pixels and height_px <= max_pixels:
            bbox_geom = box(aligned_minx, aligned_miny, aligned_maxx, aligned_maxy)
            geometries = [
                {"geometry": bbox_geom, "width": width_px, "height": height_px}
            ]
        else:
            tiles_x = max(1, math.ceil(width_px / max_pixels))
            tiles_y = max(1, math.ceil(height_px / max_pixels))

            widths = self._split_pixel_counts(width_px, tiles_x)
            heights = self._split_pixel_counts(height_px, tiles_y)

            geometries = []
            y_min = aligned_miny
            for tile_h in heights:
                y_max = y_min + tile_h * self.resolution_y
                x_min = aligned_minx
                for tile_w in widths:
                    x_max = x_min + tile_w * self.resolution_x
                    geometries.append(
                        {
                            "geometry": box(x_min, y_min, x_max, y_max),
                            "width": tile_w,
                            "height": tile_h,
                        }
                    )
                    x_min = x_max
                y_min = y_max

        # Create GeoDataFrame and renumber sequentially
        bbox_gdf = gpd.GeoDataFrame(geometries, crs=CRS.from_epsg(self.crs))
        bbox_gdf["id"] = range(1, len(bbox_gdf) + 1)
        bbox_gdf["identifier"] = bbox_gdf["id"].astype(str)

        # Reorder columns to match expected format
        bbox_gdf = bbox_gdf[["id", "identifier", "width", "height", "geometry"]]

        return bbox_gdf
