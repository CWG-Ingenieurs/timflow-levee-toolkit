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


def test_plot_bro_locations_square_around_extent():
    extent = [1000.0, 1350.0, 2000.0, 2300.0]  # extent of 350 x 300 m
    line = [(950.0, 2250.0), (1400.0, 2050.0)]  # cross-section beyond the extent: cut off
    f, ax = tlt.plot_bro_locations({"cpt": points(28992)}, extent, line=line, basemap=False)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    assert x1 - x0 == pytest.approx(y1 - y0)  # square, not widened to far-away points or the line
    assert x1 - x0 == pytest.approx(350 * 1.06)  # long side plus 3% on each side
    assert (x0 + x1) / 2 == pytest.approx(1175.0) and (y0 + y1) / 2 == pytest.approx(2150.0)  # centred
    assert ax.get_xlabel() == "x [m]"
    assert "extent" in [t.get_text() for t in ax.get_legend().get_texts()]
