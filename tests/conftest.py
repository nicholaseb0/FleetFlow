import pytest

from fleetflow.grid import DEFAULT_MAP, Warehouse

SMALL_MAP = """
#######
#C.C..#
#.SS..#
#.....#
#..D..#
#######
"""


@pytest.fixture
def small_map():
    return Warehouse.from_string(SMALL_MAP, name="small")


@pytest.fixture(scope="session")
def default_map():
    return Warehouse.from_file(DEFAULT_MAP)
