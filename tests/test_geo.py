import pytest
import json
from pathlib import Path
import geopandas as gpd
from shapely.geometry import Point, Polygon
from sh_batch_grid_builder.geo import GeoData


@pytest.fixture
def sample_geojson_file(tmp_path):
    """Create a sample GeoJSON file for testing."""
    geojson_data = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                "properties": {"name": "Origin", "value": 1},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]
                    ],
                },
                "properties": {"name": "Square", "value": 2},
            },
        ],
    }

    filepath = tmp_path / "test.geojson"
    with open(filepath, "w") as f:
        json.dump(geojson_data, f)

    return filepath


@pytest.fixture
def sample_wkt_file(tmp_path):
    """Create a sample WKT file for testing."""
    wkt_content = """POINT (0 0)
POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))
LINESTRING (0 0, 1 1, 2 2)"""

    filepath = tmp_path / "test.wkt"
    with open(filepath, "w") as f:
        f.write(wkt_content)

    return filepath


@pytest.fixture
def sample_wkt_csv_file(tmp_path):
    """Create a sample WKT CSV file for testing."""
    csv_content = """id,name,geometry
1,Point A,"POINT (0 0)"
2,Point B,"POINT (1 1)"
3,Line,"LINESTRING (0 0, 1 1)" """

    filepath = tmp_path / "test_wkt.csv"
    with open(filepath, "w") as f:
        f.write(csv_content)

    return filepath


class TestReadGeodata:
    """Test the read_geodata function."""

    def test_read_valid_geojson(self, sample_geojson_file):
        """Test reading a valid GeoJSON file."""
        gdf = read_geodata(sample_geojson_file)

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 2
        assert "name" in gdf.columns
        assert "value" in gdf.columns
        assert gdf["name"].tolist() == ["Origin", "Square"]

    def test_read_geojson_with_string_path(self, sample_geojson_file):
        """Test reading GeoJSON with a string path."""
        gdf = read_geodata(str(sample_geojson_file))
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 2

    def test_read_geojson_with_path_object(self, sample_geojson_file):
        """Test reading GeoJSON with a Path object."""
        gdf = read_geodata(Path(sample_geojson_file))
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 2

    def test_geometries_are_correct(self, sample_geojson_file):
        """Test that geometries are correctly parsed."""
        gdf = read_geodata(sample_geojson_file)

        # Check first geometry is a Point
        assert gdf.iloc[0].geometry.geom_type == "Point"
        assert gdf.iloc[0].geometry.x == 0.0
        assert gdf.iloc[0].geometry.y == 0.0

        # Check second geometry is a Polygon
        assert gdf.iloc[1].geometry.geom_type == "Polygon"
        assert gdf.iloc[1].geometry.area == 1.0

    def test_file_not_found_raises_error(self):
        """Test that FileNotFoundError is raised for non-existent files."""
        with pytest.raises(FileNotFoundError, match="Geospatial file not found"):
            read_geodata("nonexistent_file.geojson")

    def test_invalid_geojson_raises_error(self, tmp_path):
        """Test that ValueError is raised for invalid GeoJSON."""
        invalid_file = tmp_path / "invalid.geojson"
        with open(invalid_file, "w") as f:
            f.write("This is not valid JSON")

        with pytest.raises(ValueError, match="Failed to read geospatial file"):
            read_geodata(invalid_file)

    def test_properties_preserved(self, sample_geojson_file):
        """Test that all properties from GeoJSON are preserved."""
        gdf = read_geodata(sample_geojson_file)

        assert gdf.iloc[0]["name"] == "Origin"
        assert gdf.iloc[0]["value"] == 1
        assert gdf.iloc[1]["name"] == "Square"
        assert gdf.iloc[1]["value"] == 2

    def test_crs_handling(self, tmp_path):
        """Test that CRS information is preserved if present."""
        geojson_with_crs = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
                    "properties": {},
                }
            ],
        }

        filepath = tmp_path / "test_crs.geojson"
        with open(filepath, "w") as f:
            json.dump(geojson_with_crs, f)

        gdf = read_geodata(filepath)
        assert gdf.crs is not None

    def test_read_wkt_file(self, sample_wkt_file):
        """Test reading a plain WKT file."""
        gdf = read_geodata(sample_wkt_file)

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert gdf.iloc[0].geometry.geom_type == "Point"
        assert gdf.iloc[1].geometry.geom_type == "Polygon"
        assert gdf.iloc[2].geometry.geom_type == "LineString"

    def test_read_wkt_csv_file(self, sample_wkt_csv_file):
        """Test reading a CSV file with WKT geometries."""
        gdf = read_geodata(sample_wkt_csv_file)

        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert "id" in gdf.columns
        assert "name" in gdf.columns
        assert gdf.iloc[0]["name"] == "Point A"
        assert gdf.iloc[0].geometry.geom_type == "Point"

    def test_explicit_format_specification(self, sample_geojson_file):
        """Test specifying format explicitly."""
        gdf = read_geodata(sample_geojson_file, format="geojson")
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 2

    def test_unsupported_format_raises_error(self, tmp_path):
        """Test that unsupported format raises ValueError."""
        filepath = tmp_path / "test.shp"
        filepath.touch()  # Create an empty file

        with pytest.raises(ValueError, match="Unsupported format"):
            read_geodata(filepath, format="shapefile")

    def test_auto_detect_from_json_extension(self, tmp_path):
        """Test that .json extension is auto-detected as GeoJSON."""
        geojson_data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": {},
                }
            ],
        }

        filepath = tmp_path / "test.json"
        with open(filepath, "w") as f:
            json.dump(geojson_data, f)

        gdf = read_geodata(filepath)
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 1

    def test_unknown_extension_raises_error(self, tmp_path):
        """Test that unknown file extension raises ValueError."""
        filepath = tmp_path / "test.xyz"
        filepath.touch()

        with pytest.raises(ValueError, match="Cannot auto-detect format"):
            read_geodata(filepath)
