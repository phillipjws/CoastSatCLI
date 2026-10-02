"""Site GUI choices reach pipeline stages without leaking into later sites."""

import json
import argparse
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pytest
import pytz
from gooey import GooeyParser

from cli.gui_analysis import add_analysis_arguments, build_analysis_settings
from coastsat_pipeline.context import PipelineContext
from coastsat_pipeline.helpers import slope
from coastsat_pipeline.parameters import Parameters
from coastsat_pipeline.runner import PipelineRunner
from coastsat_pipeline.site_parameters import resolve_site_parameters


def gui_settings(*arguments):
    parser = GooeyParser()
    group = parser.add_argument_group("Advanced Transect Settings")
    add_analysis_arguments(parser, group)
    return build_analysis_settings(parser.parse_args(list(arguments)))


def test_gui_defaults_and_unchecked_disable_controls():
    selected = gui_settings()
    params = resolve_site_parameters(selected)
    assert params.transect_settings == Parameters.transect_settings
    assert params.outlier_settings == Parameters.outlier_settings
    assert params.slope_settings == Parameters.slope_settings
    assert params.slope_estimation_date_range == Parameters.slope_estimation_date_range
    selected = gui_settings("--disable_cass", "--skip_rejection_plots", "--skip_outlier_plots", "--skip_slope_plots")
    assert selected["transect_settings"]["CASS"] is False
    assert selected["transect_settings"]["plot_rejection_counts"] is False
    assert selected["outlier_settings"]["plot_fig"] is False
    assert selected["slope_settings"]["plot_fig"] is False


def test_full_gui_builds_tabbed_spec_without_opening_window():
    from cli import gui_init
    from gooey.python_bindings.config_generator import create_from_parser

    class ParserCaptured(Exception):
        pass

    specs = []

    def capture(parser, *args, **kwargs):
        specs.append(create_from_parser(parser, gui_init.__file__, navigation="TABBED", tabbed_groups=True))
        raise ParserCaptured

    with patch.object(argparse.ArgumentParser, "parse_args"), \
            patch.object(GooeyParser, "parse_args", capture), pytest.raises(ParserCaptured):
        gui_init.main()
    spec = specs[0]
    assert spec["tabbed_groups"] is True
    serialized = json.dumps(spec)
    for title in ("Advanced Transect Settings", "Outlier Filtering", "Beach Slope"):
        assert title in serialized
    assert '"type": "DateChooser"' in serialized
    assert '"--slope_start_date"' in serialized
    assert '"--disable_cass"' in serialized


@pytest.mark.parametrize("settings", [
    {"transect_settings": []}, {"slope_settings": None}, {"outlier_settings": "invalid"},
    {"transect_settings": {"unknown": 1}},
    {"transect_settings": {"CASS": "false"}},
    {"transect_settings": {"along_dist": float("nan")}},
    {"transect_settings": {"along_dist": 0}},
    {"transect_settings": {"past_dist": -1}},
    {"transect_settings": {"min_points": True}},
    {"transect_settings": {"min_points": 2.5}},
    {"transect_settings": {"min_points": 0}},
    {"transect_settings": {"transects_to_plot": "transect_1"}},
    {"transect_settings": {"transects_to_plot": [""]}},
    {"outlier_settings": {"max_cross_change": -10}},
    {"outlier_settings": {"otsu_threshold": [0, -0.5]}},
    {"outlier_settings": {"otsu_threshold": [-2, 0]}},
    {"outlier_settings": {"otsu_threshold": [-0.5]}},
    {"slope_settings": {"slope_min": 0}},
    {"slope_settings": {"slope_max": 0.001}},
    {"slope_settings": {"delta_slope": 1}},
    {"slope_settings": {"n0": 2.5}},
    {"slope_settings": {"n_days": 0}},
    {"slope_settings": {"freq_cutoff": 1}},
    {"slope_settings": {"delta_f": 1}},
    {"slope_settings": {"prc_conf": 2}},
    {"tide_timestep": 0}, {"default_slope": float("inf")},
    {"slope_estimation_date_range": ["2020-01-01"]},
    {"slope_estimation_date_range": ["2020-02-30", "2021-01-01"]},
    {"slope_estimation_date_range": ["2020-1-1", "2021-01-01"]},
    {"slope_estimation_date_range": ["2021-01-01", "2020-01-01"]},
])
def test_invalid_site_settings_rejected(settings):
    with pytest.raises(ValueError):
        resolve_site_parameters(settings)


def test_partial_overrides_and_rgb_dependency_are_isolated():
    selected = {"transect_settings": {"along_dist": 50, "plot_sat": True}}
    before = deepcopy(selected)
    params = resolve_site_parameters(selected)
    assert params.transect_settings["along_dist"] == 50
    assert params.transect_settings["min_points"] == Parameters.transect_settings["min_points"]
    assert params.shoreline_settings["save_sat_rgb"] is True
    params.transect_settings["transects_to_plot"].append("transect_1")
    params.slope_settings["freqs_max"] = [1, 2]
    old_site = resolve_site_parameters({})
    assert old_site.transect_settings == Parameters.transect_settings
    assert old_site.shoreline_settings == Parameters.shoreline_settings
    assert old_site.slope_settings == Parameters.slope_settings
    assert selected == before


def test_batch_setup_saves_analysis_choices_in_each_site(tmp_path):
    from cli import gui_init

    selected = gui_settings("--along_dist", "45", "--min_points", "5", "--plot_sat",
                            "--transects_to_plot", "transect_1, transect_2",
                            "--slope_start_date", "2018-01-01", "--slope_end_date", "2020-01-01",
                            "--tide_timestep", "1800", "--default_slope", "0.15")
    aois = [tmp_path / f"aoi{i}.kml" for i in range(2)]
    for aoi in aois:
        aoi.write_text("test AOI")
    with patch.object(gui_init, "load_aoi_and_shoreline", return_value=(None, None)), \
            patch.object(gui_init, "create_and_save_reference_shoreline"), \
            patch.object(gui_init, "generate_and_save_transects"):
        results, failures = gui_init.init_sites(
            aois, ["site1", "site2"], 32610, None,
            {"method": "fes", "fes_config": "fes.yaml"}, tmp_path,
            {"spacing": 100, "length": 200, "offset_ratio": 0.75, "skip_threshold": 300},
            analysis_settings=selected,
        )
    assert failures == []
    assert len(results) == 2
    for site in results:
        saved = json.loads(site["settings_path"].read_text())
        for key in selected:
            assert saved[key] == selected[key]
        params = resolve_site_parameters(saved)
        assert params.slope_estimation_date_range[0] == pytz.utc.localize(datetime(2018, 1, 1))
        assert params.shoreline_settings["save_sat_rgb"] is True


def test_runner_reads_site_overrides_again_for_checkpoint_reruns(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"transect_settings": {"along_dist": 55}, "default_slope": 0.2}))
    context = PipelineContext(path, global_settings={"sitename": "test"})
    seen = []

    def run_stage(context, params):
        seen.append((params.transect_settings["along_dist"], params.default_slope))
        params.transect_settings["along_dist"] = 1000

    stage = SimpleNamespace(name="test", should_run=Mock(return_value=True), log_start=Mock(),
                            log_end=Mock(), run=run_stage)
    runner = PipelineRunner([stage])
    with patch.object(runner, "init_log_file"), patch("coastsat_pipeline.runner.checkpoints.save_context"):
        runner.run(context)
        path.write_text("{}")
        runner.run(context)
    assert seen == [(55, 0.2), (Parameters.transect_settings["along_dist"], Parameters.default_slope)]
    assert stage.should_run.call_args.args[1].transect_settings["along_dist"] == 1000
    assert Parameters.transect_settings["along_dist"] == 35


def test_custom_slope_window_reaches_filter_and_plot_toggle(tmp_path):
    params = resolve_site_parameters(gui_settings("--slope_start_date", "2018-01-01", "--slope_end_date", "2020-01-01",
                                                 "--skip_slope_plots", "--tide_timestep", "1800"))
    dates = [pytz.utc.localize(datetime(year, 1, 1)) for year in (2018, 2019, 2020, 2021)]
    tides = np.arange(4, dtype=float)
    settings = {"filepath": str(tmp_path)}
    output = {"dates": dates, "satname": ["L8"] * 4}
    cross = {"transect_1": np.array([10, 20, 30, 40])}
    with patch.object(slope, "_compute_tides", return_value=(None, dates, tides, dates, tides)) as compute, \
            patch.object(slope, "_estimate_slopes", return_value=({"transect_1": 0.1}, {})) as estimate:
        slope.run_slope_estimation(settings, cross, output, params.slope_estimation_date_range,
                                   params.tide_timestep, params.slope_settings, params.default_slope)
    assert compute.call_args.args[-1] == 1800
    assert estimate.call_args.args[1] == dates[:2]
    np.testing.assert_array_equal(estimate.call_args.args[3]["transect_1"], [10, 20])
    assert estimate.call_args.args[4] is False
    assert estimate.call_args.args[5]["plot_fig"] is False
    assert "freqs_max" not in params.slope_settings


def test_empty_custom_window_is_not_silently_ignored():
    dates = [pytz.utc.localize(datetime(2021, 1, 1))]
    window = [pytz.utc.localize(datetime(year, 1, 1)) for year in (2018, 2020)]
    with pytest.raises(ValueError, match="selected slope estimation window"):
        slope._apply_tide_filters({}, dates, np.array([1.0]), dates, np.array([1.0]),
                                 {"transect_1": np.array([10.0])}, {"satname": ["L8"]}, window)


def test_skipping_slope_figures_keeps_computation_and_creates_no_figures(tmp_path):
    settings = dict(Parameters.slope_settings, plot_fig=False)
    dates = [pytz.utc.localize(datetime(year, 1, 1)) for year in (2020, 2021)]
    with patch.object(slope.SDS_slope, "find_tide_peak", return_value=[1e-7, 2e-7]) as peak, \
            patch.object(slope.SDS_slope, "integrate_power_spectrum", return_value=(0.15, [0.1, 0.2])) as integrate, \
            patch.object(slope.SDS_slope, "plot_timestep") as timestep, \
            patch.object(slope.SDS_slope, "plot_spectrum_all") as spectrum, \
            patch.object(slope.plt, "gcf") as figure:
        estimated, _ = slope._estimate_slopes(str(tmp_path), dates, [1, 2],
                                             {"transect_1": np.array([10.0, 20.0])}, True, settings, 0.1)
    assert estimated == {"transect_1": 0.15}
    assert peak.call_args.args[2]["plot_fig"] is False
    assert integrate.call_args.args[2]["plot_fig"] is False
    timestep.assert_not_called()
    spectrum.assert_not_called()
    figure.assert_not_called()
    assert list(tmp_path.iterdir()) == []
    assert "freqs_max" not in settings


def test_missing_tidal_band_uses_selected_fallback(tmp_path):
    dates = [pytz.utc.localize(datetime(2020, 1, 1))]
    result, intervals = slope._estimate_slopes(str(tmp_path), dates, [1],
                                              {"transect_1": np.array([10.0])}, False,
                                              Parameters.slope_settings, 0.17)
    assert result == {"transect_1": 0.17}
    assert intervals == {"transect_1": (0.17, 0.17)}
