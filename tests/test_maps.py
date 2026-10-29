import contextily
import matplotlib.pyplot as plt
import pytest

import timflow_levee_toolkit as tlt
from timflow_levee_toolkit.maps import USER_AGENT


@pytest.fixture
def calls(monkeypatch):
    """Record the calls to contextily.add_basemap instead of downloading tiles."""
    recorded = []
    monkeypatch.setattr(contextily, "add_basemap", lambda ax, **kwargs: recorded.append(kwargs))
    return recorded


def test_add_basemap_sends_user_agent_and_uses_named_source(calls):
    f, ax = plt.subplots()
    assert tlt.add_basemap(ax, crs=28992, source="brt") is True
    assert calls[0]["headers"] == {"User-Agent": USER_AGENT}  # OpenStreetMap blocks requests without it
    assert calls[0]["source"] == tlt.BASEMAPS["brt"][0]
    assert calls[0]["attribution"] == "Kaartgegevens © Kadaster"
    assert calls[0]["crs"] == 28992
    plt.close(f)


def test_add_basemap_default_is_openstreetmap(calls):
    f, ax = plt.subplots()
    tlt.add_basemap(ax, crs="EPSG:28992")
    assert "openstreetmap" in calls[0]["source"]
    plt.close(f)


def test_add_basemap_without_internet_gives_message(monkeypatch, capsys):
    def offline(ax, **kwargs):
        raise ConnectionError("no internet")

    monkeypatch.setattr(contextily, "add_basemap", offline)
    f, ax = plt.subplots()
    assert tlt.add_basemap(ax, crs=28992) is False
    assert "No background map" in capsys.readouterr().out
    plt.close(f)


def test_square_extent():
    f, ax = plt.subplots()
    tlt.square_extent(ax, [0.0, 10.0], [0.0, 200.0], margin=0.25)
    (x0, x1), (y0, y1) = ax.get_xlim(), ax.get_ylim()
    assert x1 - x0 == pytest.approx(y1 - y0)  # square
    assert y1 - y0 == pytest.approx(200 * 1.5)  # largest size plus the margin on both sides
    assert (x0 + x1) / 2 == pytest.approx(5.0) and (y0 + y1) / 2 == pytest.approx(100.0)
    tlt.square_extent(ax, [5.0], [5.0], min_size=100.0, margin=0.0)
    assert ax.get_xlim()[1] - ax.get_xlim()[0] == pytest.approx(100.0)  # a single point: minimum size
    plt.close(f)
