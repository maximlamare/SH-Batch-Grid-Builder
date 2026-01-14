from typing import Tuple
from pyproj import CRS


def get_crs_data(target_epsg: int) -> Tuple[float, float]:
    crs = CRS.from_epsg(target_epsg)

    origin_x = 0.0
    origin_y = 0.0

    if crs.is_projected:
        for param in crs.coordinate_operation.params:
            if "easting" in param.name.lower() or "false easting" in param.name.lower():
                origin_x = param.value
            if (
                "northing" in param.name.lower()
                or "false northing" in param.name.lower()
            ):
                origin_y = param.value

    return origin_x, origin_y


def get_crs_units(target_epsg: int) -> str:
    """
    Get the units of the CRS.
    
    Args:
        target_epsg: EPSG code
        
    Returns:
        String describing the units (e.g., "degrees", "metre", "meter", "foot", etc.)
    """
    crs = CRS.from_epsg(target_epsg)
    
    if crs.is_geographic:
        return "degrees"
    elif crs.is_projected:
        # Get units from axis info
        if crs.axis_info:
            unit_name = crs.axis_info[0].unit_name.lower()
            # Normalize common variations
            if unit_name in ["metre", "meter", "m"]:
                return "meters"
            elif unit_name in ["degree", "degrees", "deg"]:
                return "degrees"
            elif unit_name in ["foot", "feet", "ft"]:
                return "feet"
            else:
                return unit_name
        else:
            # Default for projected CRS is usually meters
            return "meters"
    else:
        # Fallback - try to get from CRS string
        crs_str = str(crs).lower()
        if "degree" in crs_str:
            return "degrees"
        elif "metre" in crs_str or "meter" in crs_str:
            return "meters"
        else:
            return "unknown"
