"""Exercise saved settings with real, hidden Gooey controls."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import wx
from gooey.gui.components.config import TabbedConfigPage
from gooey.gui.lang import i18n

from cli import gui_init
from cli.gui_presets import FormSettings, PRESET_FORMAT, PRESET_VERSION, attach_settings_menu


@pytest.fixture(scope="module")
def wx_app():
    existing = wx.GetApp()
    app = existing or wx.App(False)
    yield app
    app.Yield()
    if existing is None:
        app.Destroy()


@pytest.fixture(scope="module")
def config(wx_app):
    spec = gui_init.build_gui_spec(gui_init.build_parser())
    i18n.load(spec["language_dir"], spec["language"], spec["encoding"])
    frame = wx.Frame(None)
    config = TabbedConfigPage(frame, next(iter(spec["widgets"].values())), spec)
    yield config
    frame.Destroy()


@pytest.fixture
def form(config):
    settings = FormSettings(config)
    yield settings
    settings.apply(settings.defaults)


def test_all_form_values_round_trip_including_unfinished_inputs(form, tmp_path):
    assert len(form.widgets) > 60
    choices = {
        "--base_dir": "C:/projects/Coastal Sites", "--sitename": "Example coast",
        "--shoreline": "C:/inputs/shoreline file.geojson",
        "--aois": "C:/inputs/first.kml|C:/inputs/second.kml",
        "--tide_method": "csv", "--tide_csv": "C:/inputs/tides.csv",
        "--fes_config": "", "--beach_slope": "0.08", "--engine": "legacy",
        "--epsg": "", "--transect_spacing": "125.5", "--cloud_thresh": "unfinished",
        "--sat_list": ["L8", "S2"], "--months": "6,7 8",
        "--start_date": "2000-01-02", "--end_date": "2026-09-30",
        "--enable_tide_filter": True, "--run_now": False, "--delete_tifs": True,
        "--save_detection_plots": False, "--plot_cloud_cover": False,
        "--disable_cass": True, "--skip_slope_plots": True,
    }
    form.apply(choices)
    expected = form.capture()
    path = tmp_path / "my settings.json"
    form.save(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["format"] == PRESET_FORMAT
    assert payload["version"] == PRESET_VERSION
    form.apply(form.defaults)
    form.load(path)
    assert form.capture() == expected
    # Listbox restoration must replace all five initially selected missions.
    assert form.capture()["--sat_list"] == ["L8", "S2"]
    form.load(path)
    assert form.capture() == expected


def test_empty_selection_and_unchecked_boxes_replace_previous_values(form, tmp_path):
    form.apply({"--sat_list": [], "--engine": None, "--run_now": False})
    path = tmp_path / "empty.json"
    form.save(path)
    form.apply({"--sat_list": ["L5", "S2"], "--engine": "pipeline", "--run_now": True})
    form.load(path)
    assert form.capture()["--sat_list"] == []
    assert form.capture()["--engine"] is None
    assert form.capture()["--run_now"] is False


@pytest.mark.parametrize("payload", [
    [], {"inputs": {"sitename": "site"}},
    {"format": PRESET_FORMAT, "version": 99, "values": {}},
    {"format": PRESET_FORMAT, "version": True, "values": {}},
    {"format": PRESET_FORMAT, "version": 1, "values": []},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--unknown": "value"}},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--run_now": "false"}},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--cloud_thresh": 0.5}},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--engine": "unknown"}},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--sat_list": ["S3"]}},
    {"format": PRESET_FORMAT, "version": 1, "values": {"--sat_list": [["S2"]]}},
])
def test_invalid_files_leave_entire_form_unchanged(form, tmp_path, payload):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = form.capture()
    with pytest.raises(ValueError):
        form.load(path)
    assert form.capture() == original


def test_malformed_json_and_missing_file_leave_form_unchanged(form, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{broken", encoding="utf-8")
    original = form.capture()
    with pytest.raises(ValueError):
        form.load(path)
    with pytest.raises(OSError):
        form.load(tmp_path / "missing.json")
    assert form.capture() == original


def test_fields_missing_from_older_preset_use_initial_defaults(form, tmp_path):
    path = tmp_path / "older.json"
    path.write_text(json.dumps({
        "format": PRESET_FORMAT, "version": 1, "values": {"--sitename": "old site"},
    }), encoding="utf-8")
    form.apply({"--run_now": False, "--sat_list": ["L8"]})
    form.load(path)
    assert form.capture() == {**form.defaults, "--sitename": "old site"}


def test_failed_save_preserves_previous_file(form, tmp_path):
    path = tmp_path / "existing.json"
    path.write_text("existing settings", encoding="utf-8")
    with patch("cli.gui_presets.os.replace", side_effect=OSError("write failed")):
        with pytest.raises(OSError):
            form.save(path)
    assert path.read_text() == "existing settings"
    assert list(tmp_path.iterdir()) == [path]


def test_file_menu_saves_and_opens_without_running_setup(form, tmp_path, wx_app):
    frame = wx.Frame(None)
    frame.SetMenuBar(wx.MenuBar())
    frame.navbar = Mock()
    frame.navbar.getActiveConfig.return_value = form.config
    frame.clientRunner = Mock()
    frame.clientRunner.running.return_value = False
    frame.showSettings = Mock()
    settings = attach_settings_menu(frame)
    path = tmp_path / "menu.json"

    def click(item_id):
        frame.ProcessWindowEvent(wx.CommandEvent(wx.EVT_MENU.typeId, item_id))

    try:
        with patch("cli.gui_init.run_setup") as run, \
                patch.object(wx, "FileDialog") as dialog, patch.object(wx, "MessageBox") as error:
            chooser = dialog.return_value.__enter__.return_value
            chooser.ShowModal.return_value = wx.ID_OK
            chooser.GetPath.return_value = str(path)
            form.apply({"--sitename": "from menu", "--run_now": False, "--sat_list": ["L8"]})
            saved = form.capture()
            click(wx.ID_SAVE)
            assert path.exists()
            form.apply(settings.defaults)
            click(wx.ID_OPEN)
            assert form.capture() == saved
            frame.showSettings.assert_called_once()
            run.assert_not_called()
            error.assert_not_called()
            assert "Opened settings:" in frame.GetStatusBar().GetStatusText()
            # Cancel and running-state guards leave the form untouched.
            chooser.ShowModal.return_value = wx.ID_CANCEL
            click(wx.ID_OPEN)
            assert form.capture() == saved
            frame.clientRunner.running.return_value = True
            dialog.reset_mock()
            click(wx.ID_OPEN)
            click(wx.ID_SAVE)
            dialog.assert_not_called()
    finally:
        frame.Destroy()


def test_settings_toolbar_in_actual_gooey_window(wx_app, tmp_path):
    from gooey.gui.application import _build_app, GooeyApplication
    from gooey.gui.pubsub import pub

    # Build the complete Gooey window, while keeping it hidden and isolating its
    # event subscriptions. A plain wx.Frame would miss Gooey layout regressions.
    spec = gui_init.build_gui_spec(gui_init.build_parser())
    with patch.dict(pub.registry, clear=True):
        with patch.object(GooeyApplication, "Show"):
            _, frame = _build_app(spec, wx_app)
        try:
            settings = attach_settings_menu(frame)
            toolbar = frame.GetToolBar()
            assert toolbar.IsShown()
            assert toolbar.GetToolsCount() == 2
            assert toolbar.FindById(wx.ID_OPEN).GetLabel() == "Load Settings..."
            assert toolbar.FindById(wx.ID_SAVE).GetLabel() == "Save Settings..."
            assert frame.GetMenuBar().GetMenuLabel(0) == "&File"
            assert toolbar.GetSize().width > 0
            assert toolbar.GetSize().height > 0
            config = frame.navbar.getActiveConfig()
            config.notebook.ChangeSelection(1)
            assert toolbar.IsShown()

            def click(tool_id):
                frame.ProcessWindowEvent(wx.CommandEvent(wx.EVT_TOOL.typeId, tool_id))

            path = tmp_path / "toolbar.json"
            with patch.object(wx, "FileDialog") as dialog, \
                    patch.object(wx, "MessageBox") as error, \
                    patch.object(frame.clientRunner, "run") as run:
                chooser = dialog.return_value.__enter__.return_value
                chooser.ShowModal.return_value = wx.ID_OK
                chooser.GetPath.return_value = str(path)
                settings.apply({"--sitename": "toolbar choices", "--run_now": False,
                                "--sat_list": ["S2"]})
                saved = settings.capture()
                click(wx.ID_SAVE)
                assert path.exists()
                settings.apply(settings.defaults)
                click(wx.ID_OPEN)
                assert settings.capture() == saved
                run.assert_not_called()
                error.assert_not_called()
                assert toolbar.IsShown()
                with patch.object(frame.clientRunner, "running", return_value=True):
                    toolbar.UpdateWindowUI()
                    assert not toolbar.GetToolEnabled(wx.ID_OPEN)
                    assert not toolbar.GetToolEnabled(wx.ID_SAVE)
                toolbar.UpdateWindowUI()
                assert toolbar.GetToolEnabled(wx.ID_OPEN)
                assert toolbar.GetToolEnabled(wx.ID_SAVE)
        finally:
            frame.Destroy()
            wx_app.Yield()


def test_worker_entrypoint_parses_without_opening_gui():
    arguments = ["gui_init.py", "--ignore-gooey", "--base_dir", "sites",
                 "--sitename", "test", "--shoreline", "shoreline.geojson",
                 "--aois", "aoi.kml", "--sat_list", "L8", "S2"]
    with patch("sys.argv", arguments), patch.object(gui_init, "run_setup") as run, \
            patch("cli.gui_presets.run_settings_gui") as gui:
        gui_init.main()
    gui.assert_not_called()
    args = run.call_args.args[0]
    assert args.sitename == "test"
    assert args.sat_list == ["L8", "S2"]
    assert args.run_now is False


def test_gui_entrypoint_builds_preserved_layout_without_running_setup():
    with patch("sys.argv", ["gui_init.py"]), patch.object(gui_init, "run_setup") as run, \
            patch("cli.gui_presets.run_settings_gui") as gui:
        gui_init.main()
    run.assert_not_called()
    spec = gui.call_args.args[0]
    assert spec["navigation"] == "TABBED"
    assert spec["tabbed_groups"] is True
    assert spec["progress_regex"] == r"^PROGRESS: (?P<pct>\d+)%"
    assert Path(gui_init.__file__).name in spec["target"]
