"""Engine selection across GUI setup and subsequent CLI dispatch."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli.engine import resolve_engine


class EngineSelectionTests(unittest.TestCase):
    def test_saved_engine_and_explicit_override(self):
        self.assertEqual(resolve_engine({"engine": "pipeline"}), "pipeline")
        self.assertEqual(resolve_engine({"engine": "legacy"}, "PIPELINE"), "pipeline")
        self.assertEqual(resolve_engine({"engine": "pipeline"}, "legacy"), "legacy")

    def test_older_sites_keep_legacy_behavior(self):
        self.assertEqual(resolve_engine({}), "legacy")

    def test_invalid_engine_is_rejected(self):
        for value in ("pipline", "", None, 42):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_engine({"engine": value})

    def test_gui_saves_engine_even_without_running_analysis(self):
        from cli import gui_init

        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            aoi = base / "aoi.kml"
            aoi.write_text("test AOI", encoding="utf-8")
            for engine in ("pipeline", "legacy"):
                with self.subTest(engine=engine), \
                        patch("cli.geo_utils.load_aoi_and_shoreline", return_value=(None, None)), \
                        patch("cli.geo_utils.create_and_save_reference_shoreline"), \
                        patch("cli.geo_utils.generate_and_save_transects"), \
                        patch("cli.dialogs.run_analysis_from_config") as run:
                    result = gui_init._init_site(
                        aoi_path=aoi,
                        sitename=engine,
                        shoreline_gdf=None,
                        tide_config={"method": "fes", "fes_config": "fes.yaml"},
                        base_dir=base,
                        epsg=32610,
                        transect_opts={"spacing": 100, "length": 200, "offset_ratio": 0.75, "skip_threshold": 300},
                        engine=engine,
                    )
                    settings = json.loads(result["settings_path"].read_text())
                    self.assertEqual(settings["engine"], engine)
                    run.assert_not_called()

    def test_gui_batch_passes_engine_to_each_site(self):
        from cli import gui_init

        with tempfile.TemporaryDirectory() as folder:
            aois = [Path(folder) / f"aoi{i}.kml" for i in range(2)]
            for aoi in aois:
                aoi.touch()
            with patch.object(gui_init, "_detect_epsg", return_value=32610), \
                    patch.object(gui_init, "_init_site", return_value={"settings_path": "settings.json", "output_dir": "outputs"}) as init:
                results, failures = gui_init.init_sites(
                    aois, ["site1", "site2"], 32610, None, {}, Path(folder), {}, engine="legacy"
                )
                self.assertEqual(len(results), 2)
                self.assertEqual(failures, [])
                self.assertEqual([call.kwargs["engine"] for call in init.call_args_list], ["legacy", "legacy"])

    def test_dispatch_uses_saved_engine_and_run_override(self):
        from cli import dialogs

        cases = [
            ({"engine": "pipeline"}, None, "pipeline"),
            ({"engine": "legacy"}, None, "legacy"),
            ({}, None, "legacy"),
            ({"engine": "pipeline"}, "legacy", "legacy"),
            ({"engine": "legacy"}, "pipeline", "pipeline"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "settings.json"
            for config, override, expected in cases:
                with self.subTest(config=config, override=override):
                    config_path.write_text(json.dumps(config))
                    with patch.object(dialogs, "run_pipeline_from_config") as pipeline, \
                            patch.object(dialogs.subprocess, "Popen") as popen:
                        popen.return_value.__enter__.return_value.stdout.read.return_value = b""
                        popen.return_value.__enter__.return_value.wait.return_value = 0
                        self.assertEqual(dialogs.run_analysis_from_config(config_path, engine=override), 0)
                        if expected == "pipeline":
                            pipeline.assert_called_once_with(config_path)
                            popen.assert_not_called()
                        else:
                            pipeline.assert_not_called()
                            popen.assert_called_once()
                    self.assertEqual(json.loads(config_path.read_text()), config)

    def test_cli_omitted_engine_uses_gui_saved_setting(self):
        from cli import dialogs, file_utils, geo_utils
        from typer.testing import CliRunner

        # The CLI script uses sibling imports when launched by its file path.
        with patch.dict(sys.modules, {"dialogs": dialogs, "file_utils": file_utils, "geo_utils": geo_utils}):
            from cli import CoastsatCLI

        with tempfile.TemporaryDirectory() as folder:
            config_path = Path(folder) / "settings.json"
            config_path.write_text(json.dumps({"engine": "pipeline"}))
            with patch.object(dialogs, "run_pipeline_from_config") as pipeline, \
                    patch.object(dialogs.subprocess, "Popen") as popen:
                result = CliRunner().invoke(CoastsatCLI.app, ["run", "--config", str(config_path)])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("Analysis engine: pipeline", result.output)
                pipeline.assert_called_once_with(config_path)
                popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
