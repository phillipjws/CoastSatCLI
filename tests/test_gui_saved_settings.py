"""The full setup form persists selected imagery and extraction parameters."""

import argparse
import json
from unittest.mock import patch

import pytest
from gooey import GooeyParser
from gooey.python_bindings.config_generator import create_from_parser

from cli import gui_init
from cli.gui_analysis import build_shoreline_settings
from cli.gui_download import build_download_settings
from coastsat_pipeline.context import PipelineContext
from coastsat_pipeline.helpers.config import build_settings
from coastsat_pipeline.helpers.download import download_images
from coastsat_pipeline.parameters import Parameters
from coastsat_pipeline.site_parameters import resolve_site_parameters
from coastsat_pipeline.stages.detection_stage import DetectionStage


def setup_parser():
    captured = []

    class Captured(Exception):
        pass

    def capture(parser, *args, **kwargs):
        captured.append(parser)
        raise Captured

    with patch.object(argparse.ArgumentParser, "parse_args"), \
            patch.object(GooeyParser, "parse_args", capture), pytest.raises(Captured):
        gui_init.main()
    return captured[0]


def parse(parser, *args):
    return parser.parse_args([
        "--base_dir", "sites", "--sitename", "test", "--shoreline", "shoreline.geojson",
        "--aois", "aoi.kml", *args,
    ])


def test_download_form_accepts_comma_and_space_filters_and_omits_empty_tiles():
    args = parse(setup_parser(), "--sat_list", "L8", "S2", "--months", "6,7", "8",
                 "--excluded_epsg_codes", "32609,32610", "--landsat_wrs", "055022",
                 "--s2_tile", "09UVA", "--skip_l7_slc")
    settings = build_download_settings(args)
    assert settings["sat_list"] == ["L8", "S2"]
    assert settings["months"] == [6, 7, 8]
    assert settings["excluded_epsg_codes"] == ["32609", "32610"]
    assert settings["LandsatWRS"] == "055022"
    assert settings["S2tile"] == "09UVA"
    assert settings["skip_L7_SLC"] is True
    defaults = build_download_settings(parse(setup_parser()))
    assert "months" not in defaults
    assert "LandsatWRS" not in defaults
    assert "S2tile" not in defaults


def test_checked_gui_defaults_can_be_unchecked():
    parser = setup_parser()
    spec = create_from_parser(parser, gui_init.__file__, navigation="TABBED", tabbed_groups=True)

    def widgets(value):
        if isinstance(value, dict):
            if "id" in value and "data" in value:
                yield value
            for item in value.values():
                yield from widgets(item)
        elif isinstance(value, list):
            for item in value:
                yield from widgets(item)

    by_id = {widget["id"]: widget for widget in widgets(spec)}
    for flag in ("--run_now", "--save_detection_plots", "--plot_cloud_cover"):
        assert by_id[flag]["options"]["initial_value"] is True
        assert by_id[flag]["data"]["default"] is False
    args = parse(parser)
    assert args.run_now is False
    selected = build_shoreline_settings(args)
    assert selected["save_detection_plots"] is False
    assert selected["plot_cloud_cover"] is False


@pytest.mark.parametrize("settings", [
    {"cloud_thresh": -0.1}, {"cloud_thresh": 1.1},
    {"s2cloudless_prob": -1}, {"s2cloudless_prob": 101}, {"s2cloudless_prob": 1.5},
    {"dist_clouds": -1}, {"dist_clouds": float("nan")},
    {"min_length_sl": 0}, {"max_dist_ref": 0}, {"min_beach_area": -1},
    {"sand_color": "blue"}, {"cloud_mask_issue": "false"}, {"pan_off": 1},
    {"unknown": 1},
])
def test_invalid_shoreline_settings_rejected(settings):
    with pytest.raises(ValueError):
        resolve_site_parameters({"shoreline_settings": settings})


def test_form_choices_survive_batch_setup_and_reach_download_and_detection(tmp_path):
    parser = setup_parser()
    shoreline_path = tmp_path / "shoreline.geojson"
    shoreline_path.write_text("test shoreline")
    aois = [tmp_path / f"aoi{i}.kml" for i in range(2)]
    for aoi in aois:
        aoi.write_text("test AOI")
    args = parser.parse_args([
        "--base_dir", str(tmp_path), "--sitename", "batch", "--shoreline", str(shoreline_path),
        "--aois", *map(str, aois), "--epsg", "32610", "--fes_config", "fes.yaml",
        "--sat_list", "L8", "S2", "--start_date", "2010-01-01", "--end_date", "2025-01-01",
        "--months", "6,7", "--cloud_thresh", "0.2", "--cloud_mask_issue", "--pan_off",
        "--dist_clouds", "45", "--sand_color", "dark", "--save_detection_plots",
        "--plot_sat", "--transects_to_plot", "transect_1",
    ])
    with patch.object(argparse.ArgumentParser, "parse_args"), \
            patch.object(GooeyParser, "parse_args", return_value=args), \
            patch.object(gui_init.gpd, "read_file"), \
            patch.object(gui_init, "load_aoi_and_shoreline", return_value=(None, None)), \
            patch.object(gui_init, "create_and_save_reference_shoreline"), \
            patch.object(gui_init, "generate_and_save_transects"), \
            patch.object(gui_init, "run_sites") as run:
        gui_init.main()
    run.assert_not_called()
    paths = sorted(tmp_path.glob("*/settings.json"))
    assert len(paths) == 2
    for path in paths:
        saved = json.loads(path.read_text())
        assert saved["download_settings"]["sat_list"] == ["L8", "S2"]
        assert saved["download_settings"]["dates"] == ["2010-01-01", "2025-01-01"]
        assert saved["download_settings"]["months"] == [6, 7]
        assert saved["shoreline_settings"]["cloud_thresh"] == 0.2
        assert saved["shoreline_settings"]["pan_off"] is True
        assert saved["shoreline_settings"]["plot_cloud_cover"] is False
        params = resolve_site_parameters(saved)
        assert params.shoreline_settings["save_sat_rgb"] is True
        with patch("coastsat_pipeline.helpers.config.SDS_tools.polygon_from_kml", return_value=[[[0, 0], [1, 1]]]), \
                patch("coastsat_pipeline.helpers.config.SDS_tools.smallest_rectangle", side_effect=lambda value: value):
            settings = build_settings(path, Parameters.download_filters)
        with patch("coastsat_pipeline.helpers.download.SDS_download.retrieve_images", return_value={}) as download:
            download_images(settings, Parameters.download_filters)
        assert download.call_args.args[0]["sat_list"] == ["L8", "S2"]
        context = PipelineContext(path, global_settings=settings, metadata={"download": {}})
        with patch("coastsat_pipeline.stages.detection_stage.run_batch_shoreline_detection", return_value={}) as detect:
            DetectionStage().run(context, params)
        extraction = detect.call_args.args[2]
        assert extraction["cloud_thresh"] == 0.2
        assert extraction["dist_clouds"] == 45
        assert extraction["sand_color"] == "dark"
        assert extraction["save_sat_rgb"] is True
    assert Parameters.shoreline_settings["cloud_thresh"] == 0.5
    assert Parameters.shoreline_settings["save_sat_rgb"] is False
