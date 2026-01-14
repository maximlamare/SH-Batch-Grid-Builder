"""
SH Batch Grid Builder

A tool for generating aligned bounding boxes and pixelated geometries from AOI files.
"""

from sh_batch_grid_builder.geo import GeoData
from sh_batch_grid_builder.crs import get_crs_data, get_crs_units

__version__ = "0.1.0"
__all__ = ["GeoData", "get_crs_data", "get_crs_units"]