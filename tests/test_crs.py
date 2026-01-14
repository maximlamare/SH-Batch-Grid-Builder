import pytest
from sh_batch_grid_builder.crs import get_crs_data


class TestGetCrsData:
    """Test the get_crs_data function with known EPSG codes and their expected origins."""

    def test_epsg_4326(self):
        origin_x, origin_y = get_crs_data(4326)
        assert origin_x == 0.0
        assert origin_y == 0.0

    def test_epsg_3857(self):
        origin_x, origin_y = get_crs_data(3857)
        assert origin_x == 0.0
        assert origin_y == 0.0

    def test_epsg_3035(self):
        origin_x, origin_y = get_crs_data(3035)
        assert origin_x == 4321000
        assert origin_y == 3210000

    def test_epsg_32633(self):
        origin_x, origin_y = get_crs_data(32633)
        assert origin_x == 500000
        assert origin_y == 0

    def test_epsg_2154(self):
        origin_x, origin_y = get_crs_data(2154)
        assert origin_x == 700000
        assert origin_y == 6600000
