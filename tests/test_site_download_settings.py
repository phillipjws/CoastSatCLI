"""Site overrides reach the downloader without changing global defaults."""

import json
from copy import deepcopy
from unittest.mock import patch

import pytest

from coastsat_pipeline.download_settings import resolve_download_settings
from coastsat_pipeline.helpers.config import build_settings
from coastsat_pipeline.helpers.download import download_images


DEFAULTS = {"dates": ["1984-01-01", "2025-01-01"], "sat_list": ["L5", "L8"]}


@pytest.mark.parametrize("overrides", [
    {"dates": ["2020-02-30", "2025-01-01"]},
    {"dates": ["2025-01-01", "2020-01-01"]},
    {"dates": ["20200101", "2025-01-01"]},
    {"dates": ["2020-01-01", "2020-01-01"]},
    {"sat_list": []}, {"sat_list": ["S3"]}, {"sat_list": ["S2", "S2"]},
    {"months": [True]}, {"months": [0]}, {"months": []},
    {"skip_L7_SLC": "false"}, {"excluded_epsg_codes": [False]},
    {"LandsatWRS": "123"}, {"S2tile": "bad"},
    {"satellites": ["S2"]}, [],
])
def test_invalid_download_settings(overrides):
    with pytest.raises(ValueError):
        resolve_download_settings(DEFAULTS, overrides)


def test_partial_overrides_are_isolated():
    original = deepcopy(DEFAULTS)
    override = {"sat_list": ["S2"]}
    first = resolve_download_settings(DEFAULTS, override)
    first["dates"][0] = "2000-01-01"
    first["sat_list"].append("L9")
    assert DEFAULTS == original
    assert override == {"sat_list": ["S2"]}
    assert resolve_download_settings(DEFAULTS) == original


def test_optional_filters():
    selected = resolve_download_settings(DEFAULTS, {
        "months": [6, 7], "excluded_epsg_codes": [32609, "32610"],
        "LandsatWRS": "055022", "S2tile": "09UVA", "skip_L7_SLC": True,
    })
    assert selected["months"] == [6, 7]


def write_config(tmp_path, download_settings=None, tide=None):
    config = {
        "inputs": {
            "sitename": "test", "aoi_path": "aoi.kml",
            "reference_shoreline": "ref.geojson", "transects": "transects.geojson",
            **(tide or {}),
        },
        "output_dir": "outputs", "output_epsg": 32610,
    }
    if download_settings is not None:
        config["download_settings"] = download_settings
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(config))
    return path


def load_config(path):
    with patch("coastsat_pipeline.helpers.config.SDS_tools.polygon_from_kml", return_value=[[[0, 0], [1, 1]]]), \
         patch("coastsat_pipeline.helpers.config.SDS_tools.smallest_rectangle", side_effect=lambda polygon: polygon):
        return build_settings(path, DEFAULTS)


def test_saved_selection_reaches_downloader(tmp_path):
    path = write_config(tmp_path, {"sat_list": ["S2"], "dates": ["2020-01-01", "2024-01-01"]})
    before = path.read_text()
    settings = load_config(path)
    with patch("coastsat_pipeline.helpers.download.SDS_download.retrieve_images", return_value={}) as retrieve:
        download_images(settings, DEFAULTS)
    passed = retrieve.call_args.args[0]
    assert passed["sat_list"] == ["S2"]
    assert passed["dates"] == ["2020-01-01", "2024-01-01"]
    assert settings["sat_list"] == ["S2"]
    assert path.read_text() == before


def test_old_settings_keep_defaults(tmp_path):
    settings = load_config(write_config(tmp_path))
    assert settings["dates"] == DEFAULTS["dates"]
    assert settings["sat_list"] == DEFAULTS["sat_list"]


def test_csv_tide_values_and_paths_survive_loading(tmp_path):
    path = write_config(tmp_path, tide={
        "tide_csv_path": "tides.csv", "reference_elevation": -0.5, "beach_slope": 0.08,
    })
    settings = load_config(path)
    assert settings["tide_csv_path"] == str(tmp_path / "tides.csv")
    assert settings["reference_elevation"] == -0.5
    assert settings["beach_slope"] == 0.08
    assert settings["tide_cfg"].mode == "csv"
    assert settings["tide_cfg"].beach_slope == 0.08


def test_fes_path_is_relative_to_site(tmp_path):
    settings = load_config(write_config(tmp_path, tide={"fes_config": "fes.yaml"}))
    assert settings["fes_config"] == str(tmp_path / "fes.yaml")
    assert settings["tide_cfg"].mode == "fes"


@pytest.mark.parametrize("value", [0, -1, True, float("inf")])
def test_invalid_csv_slope(tmp_path, value):
    with pytest.raises(ValueError):
        load_config(write_config(tmp_path, tide={"beach_slope": value}))
