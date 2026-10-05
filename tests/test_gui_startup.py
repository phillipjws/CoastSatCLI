"""Keep processing dependencies out of the setup window's startup path."""

from pathlib import Path
import subprocess
import sys
import textwrap
from types import SimpleNamespace
from unittest.mock import patch

from cli import gui_init


def test_setup_gui_starts_without_importing_processing_stack():
    # A fresh interpreter is essential: other pipeline tests already import the
    # libraries whose eager loading this regression check needs to catch.
    script = textwrap.dedent("""
        import importlib.abc
        import sys
        from unittest.mock import patch

        blocked = {
            'geopandas', 'numpy', 'matplotlib', 'scipy', 'astropy', 'ee', 'pyfes',
            'cli.geo_utils', 'cli.dialogs', 'coastsat_pipeline.cli',
            'coastsat_pipeline.registry',
        }

        class ProcessingImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
                    raise ImportError('Processing dependency loaded during startup: ' + fullname)

        sys.meta_path.insert(0, ProcessingImports())
        from cli import gui_init
        # A manual EPSG override also needs no geometry dependencies.
        assert gui_init._detect_epsg(None, 32610) == 32610
        with patch.object(sys, 'argv', ['gui_init.py']), \\
                patch('cli.gui_presets.run_settings_gui') as gui:
            gui_init.main()
        gui.assert_called_once()
        spec = gui.call_args.args[0]
        assert spec['program_name'] == 'CoastSat Site Setup'
        assert spec['tabbed_groups'] is True
        assert not blocked.intersection(sys.modules)
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_run_sites_still_calls_analysis_with_saved_engine(tmp_path):
    settings_path = tmp_path / "settings.json"
    initialized = [{"settings_path": settings_path, "output_dir": tmp_path, "sitename": "test"}]
    args = SimpleNamespace(engine="pipeline", delete_tifs=False)
    with patch("cli.dialogs.run_analysis_from_config", return_value=0) as run:
        results, failures = gui_init.run_sites(initialized, args)
    run.assert_called_once_with(settings_path, engine="pipeline")
    assert len(results) == 1
    assert failures == []
