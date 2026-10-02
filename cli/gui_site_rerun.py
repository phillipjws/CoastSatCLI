"""
Gooey-based GUI for the legacy site-rerun workflow.

Mirrors the Typer `site-rerun` command: lets you pick an existing settings.json,
optionally replace reference shoreline or transects, regenerate transects with
new parameters, clear outputs, and run analysis (legacy or pipeline).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from gooey import Gooey, GooeyParser

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cli.file_utils import clear_output_directory  # noqa: E402
from cli.geo_utils import regenerate_transects_from_config  # noqa: E402
from cli.dialogs import run_analysis_from_config  # noqa: E402

IMAGE_DIR = ROOT_DIR / "assets" / "gooey_icons"


def _load_config(settings_path: Path) -> dict:
    with open(settings_path, "r") as f:
        return json.load(f)


def _copy_if_provided(src: str | None, dest: Path, label: str) -> bool:
    if not src:
        return False
    src_path = Path(src).expanduser().resolve()
    if not src_path.exists():
        print(f"{label} not found: {src_path}")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest)
    print(f"{label} replaced with {src_path}")
    return True


@Gooey(
    program_name="CoastSat Site Rerun GUI",
    default_size=(760, 640),
    clear_before_run=True,
    show_restart_button=False,
    image_dir=str(IMAGE_DIR),
    navigation="TABBED",
    tabbed_groups=True,
)
def main() -> None:
    parser = GooeyParser(description="Rerun an existing CoastSat site with optional overrides.")
    parser.add_argument("--settings", required=True, widget="FileChooser", help="Path to existing settings.json.")
    parser.add_argument("--engine", choices=["auto", "legacy", "pipeline"], default="auto", help="Auto uses the site's saved engine (legacy for older sites); select an engine to override it for this run.")

    overrides = parser.add_argument_group("Overrides")
    overrides.add_argument("--reference_shoreline", widget="FileChooser", help="Replace reference shoreline file.")
    overrides.add_argument("--transects_file", widget="FileChooser", help="Replace transects file directly.")
    overrides.add_argument("--regen_transects", action="store_true", help="Regenerate transects using settings below.")

    tran_group = parser.add_argument_group("Transects (if regenerating)")
    tran_group.add_argument("--transect_spacing", default=100.0, type=float, help="Spacing between transects (m).")
    tran_group.add_argument("--transect_length", default=200.0, type=float, help="Transect total length (m).")
    tran_group.add_argument("--transect_offset_ratio", default=0.75, type=float, help="Fraction seaward vs landward (0-1).")
    tran_group.add_argument("--transect_skip_threshold", default=300.0, type=float, help="Skip shoreline segments shorter than this (m).")

    parser.add_argument("--clear_outputs", action="store_true", help="Clear existing outputs before rerun.")
    parser.add_argument("--run_now", action="store_true", help="Run analysis immediately after updates.")

    args = parser.parse_args()

    settings_path = Path(args.settings).expanduser().resolve()
    if not settings_path.exists():
        print(f"settings.json not found: {settings_path}")
        return

    config = _load_config(settings_path)
    base_dir = settings_path.parent

    ref_rel = config["inputs"]["reference_shoreline"]
    tran_rel = config["inputs"]["transects"]

    # Apply overrides
    _copy_if_provided(args.reference_shoreline, base_dir / ref_rel, "Reference shoreline")

    if args.transects_file:
        _copy_if_provided(args.transects_file, base_dir / tran_rel, "Transects file")

    if args.regen_transects:
        transect_settings = {
            "transect_spacing": float(args.transect_spacing),
            "transect_length": float(args.transect_length),
            "transect_offset_ratio": float(args.transect_offset_ratio),
            "transect_skip_threshold": float(args.transect_skip_threshold),
        }
        try:
            regenerate_transects_from_config(base_dir=base_dir, config=config, transect_settings=transect_settings)
        except Exception as exc:  # noqa: BLE001
            print(f"Transect regeneration failed: {exc}")
            return

    if args.clear_outputs:
        clear_output_directory(base_dir / "outputs", prompt=False)

    print("Site rerun prep complete.")

    if args.run_now:
        exit_code = run_analysis_from_config(settings_path, engine=None if args.engine == "auto" else args.engine)
        if exit_code == 0:
            print("Analysis completed successfully.")
        else:
            print(f"Analysis failed with exit code {exit_code}.")


if __name__ == "__main__":
    main()
