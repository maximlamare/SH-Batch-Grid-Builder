from pathlib import Path
from typing import Union, Optional
import math
import re
import geopandas as gpd
from shapely.geometry import box, shape
from shapely.ops import transform
from sh_batch_grid_builder.crs import get_crs_data
from pyproj import CRS


class GeoData:

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

    def read_geodata(self, filepath: Union[str, Path]):
        gdf = gpd.read_file(filepath)
        return gdf

    def create_aligned_bounding_box(self, max_pixels: int = 3500) -> gpd.GeoDataFrame:

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

        bbox_geom = box(aligned_minx, aligned_miny, aligned_maxx, aligned_maxy)

        # Create GeoDataFrame and renumber sequentially
        bbox_gdf = gpd.GeoDataFrame(
            [{"geometry": bbox_geom}], crs=CRS.from_epsg(self.crs)
        )
        bbox_gdf["id"] = range(1, len(bbox_gdf) + 1)
        bbox_gdf["identifier"] = bbox_gdf["id"].astype(str)

        # Reorder columns to match expected format
        bbox_gdf = bbox_gdf[["id", "identifier", "geometry"]]

        return bbox_gdf
