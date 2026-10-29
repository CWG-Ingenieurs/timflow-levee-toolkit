import geopandas as gpd
import pytest
from shapely.geometry import Point

import timflow_levee_toolkit as tlt

brodata = pytest.importorskip("brodata")  # optional dependency: extra 'subsurface'


def points(crs):
    return gpd.GeoDataFrame({"id": ["a"]}, geometry=[Point(105700.0, 427400.0)], crs=crs)


def test_bro_locations_get_rd_new_when_crs_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(brodata.cpt, "get_characteristics", lambda extent: points(28992))
    monkeypatch.setattr(brodata.bhr, "get_characteristics", lambda extent: points(28992))
    monkeypatch.setattr(brodata.gmw, "get_characteristics", lambda extent: points(28992))
    monkeypatch.setattr(brodata.dino, "get_boormonsterprofiel", lambda extent: points(None))  # as delivered

    locations = tlt.get_bro_locations([105650, 106000, 427250, 427550])
    assert all(gdf.crs.to_epsg() == 28992 for gdf in locations.values())

    gpkg = tmp_path / "bro_locations.gpkg"
    tlt.save_bro_locations(locations, gpkg)
    assert gpd.read_file(gpkg, layer="gbo").crs.to_epsg() == 28992
