"""
Gooey-based GUI for the legacy init workflow (settings.json creation).

Replicates the legacy Typer `init` flow: sets up project folders, detects EPSG,
clips shoreline, generates transects, writes settings.json, and optionally runs
analysis via the selected engine (legacy scripts or new pipeline).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, List
from datetime import datetime, date
import csv

from gooey import GooeyParser

if TYPE_CHECKING:
    import geopandas as gpd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Keep the form import path lightweight. Geospatial and analysis dependencies
# are loaded by the worker functions only after the user submits the form.
from cli.engine import resolve_engine  # noqa: E402
from cli.gui_analysis import add_analysis_arguments, build_analysis_settings, build_shoreline_settings  # noqa: E402
from coastsat_pipeline.download_settings import resolve_download_settings  # noqa: E402
from coastsat_pipeline.parameters import Parameters  # noqa: E402
from coastsat_pipeline.site_parameters import SITE_PARAMETER_KEYS, resolve_site_parameters  # noqa: E402

IMAGE_DIR = ROOT_DIR / "assets" / "gooey_icons"


def _split_paths(raw) -> List[str]:
    """
    Gooey returns multi-file selections as a separator-delimited string.
    Support '|', ';', ',' and newlines to be tolerant across platforms.
    """
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]

    parts: List[str] = []
    for chunk in str(raw).replace("\n", "|").replace(";", "|").replace(",", "|").split("|"):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


def _validate_numeric(args) -> None:
    """Validate numeric GUI inputs early so we can fail fast with a clear message."""
    if args.transect_spacing <= 0:
        raise ValueError("Transect spacing must be > 0.")
    if args.transect_length <= 0:
        raise ValueError("Transect length must be > 0.")
    if args.transect_offset_ratio < 0 or args.transect_offset_ratio > 1:
        raise ValueError("Transect offset ratio must be between 0 and 1.")
    if args.transect_skip_threshold <= 0:
        raise ValueError("Transect skip threshold must be > 0.")
    if args.tide_method == "csv":
        float(args.beach_slope)
    if args.enable_tide_filter:
        lower = float(args.tide_lower_percentile)
        upper = float(args.tide_upper_percentile)
        if lower < 0 or upper > 100 or lower >= upper:
            raise ValueError("Tide percentiles must satisfy 0 <= lower < upper <= 100.")
    if args.epsg is not None and args.epsg <= 0:
        raise ValueError("EPSG must be a positive integer.")


def _build_tide_config(args) -> dict:
    """
    Normalize tide inputs from the GUI into the shape expected by init helpers.
    """
    tide_config: dict = {"method": args.tide_method}
    if args.tide_method == "fes":
        tide_config["fes_config"] = args.fes_config
    else:
        tide_config["tide_csv_path"] = args.tide_csv
        tide_config["reference_elevation"] = 0.0
        tide_config["beach_slope"] = float(args.beach_slope)
    if args.enable_tide_filter:
        tide_config["tide_filter"] = {
            "lower_percentile": float(args.tide_lower_percentile),
            "upper_percentile": float(args.tide_upper_percentile),
        }
    return tide_config


def _detect_epsg(aoi_path: Path, manual_epsg: int | None) -> int:
    """
    Try to auto-pick a Canadian UTM EPSG; allow manual override from the GUI.
    """
    if manual_epsg:
        return manual_epsg
    from cli.geo_utils import pick_canadian_utm_epsg

    try:
        return pick_canadian_utm_epsg(str(aoi_path))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"EPSG detection failed for {aoi_path}: {exc}")


def _init_site(
    aoi_path: Path,
    sitename: str,
    shoreline_gdf: gpd.GeoDataFrame,
    tide_config: dict,
    base_dir: Path,
    epsg: int,
    transect_opts: dict,
    engine: str = "pipeline",
    analysis_settings: dict | None = None,
    download_settings: dict | None = None,
) -> dict:
    """
    Core init routine: scaffold folders, clip shoreline to AOI, generate transects,
    write settings.json, and copy inputs into place. Returns paths for display.
    """
    engine = resolve_engine({}, engine)
    if analysis_settings is not None:
        resolve_site_parameters(analysis_settings)
    if download_settings is not None:
        resolve_download_settings(Parameters.download_filters, download_settings)
    from cli.file_utils import setup_project_directories
    from cli.geo_utils import (
        create_and_save_reference_shoreline,
        generate_and_save_transects,
        load_aoi_and_shoreline,
    )

    paths = setup_project_directories(str(base_dir), sitename)
    site_dir = Path(paths["site_dir"])
    input_dir = Path(paths["input_dir"])
    output_dir = Path(paths["output_dir"])
    aoi_dest = Path(paths["aoi_dest"])
    ref_out_path = Path(paths["ref_out_path"])
    transects_out_path = Path(paths["transects_out_path"])

    aoi_gdf, _ = load_aoi_and_shoreline(str(aoi_path), "", preloaded_shoreline=shoreline_gdf)
    reference_gdf = create_and_save_reference_shoreline(
        shoreline_gdf=shoreline_gdf, aoi_gdf=aoi_gdf, output_path=str(ref_out_path)
    )

    generate_and_save_transects(
        reference_gdf=reference_gdf,
        epsg=epsg,
        spacing=transect_opts["spacing"],
        length=transect_opts["length"],
        offset_ratio=transect_opts["offset_ratio"],
        skip_threshold=transect_opts["skip_threshold"],
        output_path=str(transects_out_path),
    )

    shutil.copy2(aoi_path, aoi_dest)

    settings = {
        "engine": engine,
        "inputs": {
            "sitename": sitename,
            "aoi_path": os.path.relpath(aoi_dest, start=site_dir),
            "reference_shoreline": os.path.relpath(ref_out_path, start=site_dir),
            "transects": os.path.relpath(transects_out_path, start=site_dir),
        },
        "output_dir": os.path.relpath(output_dir, start=site_dir),
        "output_epsg": epsg,
    }

    if tide_config["method"] == "fes":
        settings["inputs"]["fes_config"] = tide_config["fes_config"]
    else:
        settings["inputs"].update(
            {
                "tide_csv_path": tide_config["tide_csv_path"],
                "reference_elevation": tide_config["reference_elevation"],
                "beach_slope": tide_config["beach_slope"],
            }
        )
    if tide_config.get("tide_filter"):
        settings["tide_filter"] = tide_config["tide_filter"]
    if analysis_settings is not None:
        settings.update({key: analysis_settings[key] for key in SITE_PARAMETER_KEYS if key in analysis_settings})
    if download_settings is not None:
        settings["download_settings"] = download_settings

    settings_path = site_dir / "settings.json"
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=4)

    return {
        "sitename": sitename,
        "aoi_path": str(aoi_path),
        "settings_path": settings_path,
        "output_dir": output_dir,
        "epsg": epsg,
    }


def delete_tifs(folder: Path):
    """Delete all tif files inside a folder"""
    count = 0
    for tif in folder.rglob("*.tif"):
        try:
            tif.unlink()
            count += 1
        except Exception as e:
            print(f"Could not delete {tif}: {e}")
    print(f"Deleted {count} tif files in {folder}")

def init_sites(aoi_paths, sitenames, epsg, shoreline_gdf, tide_config, base_dir, tran_opts, engine="pipeline", analysis_settings=None, download_settings=None):
    # modified to track failures instead of exit
    init_results = []
    init_failures = []
    for aoi_path_str, sitename in zip(aoi_paths, sitenames):
        aoi_path = Path(aoi_path_str).expanduser().resolve()
        if not aoi_path.exists():
            print(f"AOI not found: {aoi_path}")
            init_failures.append((sitename, str(aoi_path), "missing AOI"))
            continue
        try:
            epsg = _detect_epsg(aoi_path, epsg)
        except Exception as exc:
            print(f"EPSG error for {aoi_path}: {exc}")
            init_failures.append((sitename, str(aoi_path), f"EPSG error: {exc}"))
            continue
        print(f"\nInitializing site '{sitename}' (EPSG {epsg})...")
        try:
            result = _init_site(
                aoi_path=aoi_path,
                sitename=sitename,
                shoreline_gdf=shoreline_gdf,
                tide_config=tide_config,
                base_dir=base_dir,
                epsg=epsg,
                transect_opts=tran_opts,
                engine=engine,
                analysis_settings=analysis_settings,
                download_settings=download_settings,
            )
            init_results.append(result)
            print(f"  settings.json: {result['settings_path']}")
            print(f"  outputs dir  : {result['output_dir']}")
        except Exception as exc:
            print(f"Failed to initialize {sitename}: {exc}")
            init_failures.append((sitename, str(aoi_path), f"init failed: {exc}"))
            continue
    return init_results, init_failures

def run_sites(init_results, args):
    from cli.dialogs import run_analysis_from_config

    run_results = []
    run_failures = []
    for r in init_results:
        exit_code = run_analysis_from_config(Path(r["settings_path"]), engine=args.engine)
        site_dir = Path(r["output_dir"])
        if exit_code == 0:
            print(f"  {r['settings_path'].parent.name}: success")
            run_results.append((r['sitename'], datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))
        else:
            print(f"  {r['settings_path'].parent.name} failed: {exit_code}")
            run_failures.append((r['sitename'], exit_code, datetime.now().strftime("%Y-%m-%d_%H-%M-%S")))
        if args.delete_tifs:
            delete_tifs(site_dir) # delete tifs in site folder after run completes
    
    return run_results, run_failures

def write_to_txt(lines, path):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def write_to_init_csv(results, failures, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sitename", "aoi", "status", "reason"])
        for r in results:
            writer.writerow([r["sitename"], r["aoi_path"], "success", ""])
        for sitename, aoi, reason in failures:
            writer.writerow([sitename, aoi, "failed", reason])  

def write_to_run_csv(results, failures, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["sitename", "status", "reason", "end time"])
        for sitename, endtime in results:
            writer.writerow([sitename, "success", "", endtime])
        for sitename, reason, endtime in failures:
            writer.writerow([sitename, "failed", reason, endtime])  

def write_run_report(results, failures, base_dir, sitename):
    # header
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = base_dir/f"{sitename}_run_batch_report_{timestamp}.txt"
    csv_path = base_dir/f"{sitename}_run_batch_report_{timestamp}.csv"
    report_lines = []
    report_lines.append("CoastSat Batch Run Report\n")
    report_lines.append(f"Base directory: {base_dir}\n")
    report_lines.append(f"Total sites   : {len(results) + len(failures)}\n")
    report_lines.append(f"Successful    : {len(results)}\n")
    report_lines.append(f"Failed        : {len(results)}\n")
    report_lines.append("\n")

    # successfully run sites
    report_lines.append("Successful sites:\n")
    for sitename, endtime in results:
        line = f"{sitename} | {endtime}"
        print(f"Success: {line}")
        report_lines.append(line + "\n")

    # unsuccessfully run sites
    report_lines.append("\nFailed sites:\n")
    for sitename, reason, endtime in failures:
        line = f"{sitename} | {reason} | {endtime}"
        print(f"Failure: {line}")
        report_lines.append(line+"\n")
    
    # write to files
    write_to_txt(report_lines, report_path)
    print(f"\nRun Batch report written to:\n{report_path}")
    write_to_run_csv(results, failures, csv_path)
    print(f"Run CSV report written to:\n{csv_path}")

# initialization success/fail tracking report (TXT and CSV)
# NOTE: sitename is the parent folder for all the batched sites
def write_initialization_report(results, failures, base_dir, sitename):
    
    # header
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_path = base_dir/f"{sitename}_init_batch_report_{timestamp}.txt"
    csv_path = base_dir/f"{sitename}_init_batch_report_{timestamp}.csv"
    report_lines = []
    report_lines.append("CoastSat Batch Initialization Report\n")
    report_lines.append(f"Base directory: {base_dir}\n")
    report_lines.append(f"Total sites   : {len(results) + len(failures)}\n")
    report_lines.append(f"Successful    : {len(results)}\n")
    report_lines.append(f"Failed        : {len(results)}\n")
    report_lines.append("\n")

    # successfully initialized sites
    report_lines.append("Successful sites:\n")
    for r in results:
        line = f"{r['sitename']} | AOI: {r['aoi_path']} | settings: {r['settings_path']} | outputs: {r['output_dir']}"
        print(f"Success: {line}")
        report_lines.append(line+"\n")

    # unsuccessfully initialized sites
    report_lines.append("\nFailed sites:\n")
    for sitename, aoi, reason in failures:
        line = f"{sitename} | {aoi} | {reason}"
        print(f"Failure: {line}")
        report_lines.append(line+"\n")
    
    # write to files
    write_to_txt(report_lines, report_path)
    print(f"\nInit Batch report written to:\n{report_path}")
    write_to_init_csv(results, failures, csv_path)
    print(f"Init CSV report written to:\n{csv_path}")

def build_parser():
    """Define the setup form for both the GUI and its worker process."""
    parser = GooeyParser(prog="Options", description="Create CoastSat settings.json and optionally run analysis.")
    parser._optionals.title = "Initial Setup"
    parser.add_argument("--engine", metavar="Analysis Engine", choices=["legacy", "pipeline"], default="pipeline", help="Analysis engine saved for this site and used when running it.")
    parser.add_argument("--base_dir", metavar="Base Directory", required=True, widget="DirChooser", help="Base directory where the project folder will be created.")
    parser.add_argument("--sitename", metavar="Site Name", required=True, help="Project name (used as folder name).")
    parser.add_argument("--shoreline", metavar="Shoreline File", required=True, widget="FileChooser", help="Shoreline GeoJSON/Shapefile covering the AOI(s).")
    parser.add_argument(
        "--aois", 
        metavar="Area Of Interest KML File(s)",
        nargs="+",
        widget="MultiFileChooser",
        required=True,
        help="AOI KML file(s), choose one for single site analysis or multiple for batch analysis."
    )
    parser.add_argument("--sat_list", metavar="Satellite Missions", widget="Listbox", nargs="+", choices=["L5", "L7", "L8", "L9", "S2"], default=["L5", "L7", "L8", "L9", "S2"], help="Satellite missions to download imagery from. Pipeline engine.")
    parser.add_argument("--start_date", metavar="Start Date", widget="DateChooser", default="1984-01-01", help="Start date for imagery download (YYYY-MM-DD).")
    parser.add_argument("--end_date", metavar="End Date", widget="DateChooser", default=date.today().strftime("%Y-%m-%d"), help="End date for imagery download (YYYY-MM-DD).")
    parser.add_argument(
        "--delete_tifs",
        metavar="Delete Intermediate TIFs",
        action="store_true",
        help="Delete intermediate tif files after each site run"
    )
    parser.add_argument("--run_now", metavar="Run Analysis Now", action="store_true", gooey_options={"initial_value": True}, help="Run analysis immediately after init.")

    # Tide inputs: choose FES or CSV, optional filter.
    tide_group = parser.add_argument_group("Tidal Correction")
    tide_group.add_argument("--tide_method", metavar="Tide Correction Method", choices=["fes", "csv"], default="fes", help="Choose tide correction mode.")
    tide_group.add_argument("--fes_config", metavar="FES Config File", widget="FileChooser", help="FES2022 YAML config (for FES mode).")
    tide_group.add_argument("--tide_csv", metavar="Tide CSV File", widget="FileChooser", help="Tide CSV path (for CSV mode).")
    tide_group.add_argument("--beach_slope", metavar="Default Beach Slope", default=0.1, help="Beach slope for CSV tide mode.", type=float)

    # Tide filtering
    tide_filter_group = parser.add_argument_group("Tide Filtering", gooey_options={"group": "Tide correction"})
    tide_filter_group.add_argument("--enable_tide_filter", metavar="Enable Tide Filtering", action="store_true", help="Enable tide percentile filtering.")
    tide_filter_group.add_argument("--tide_lower_percentile", metavar="Lower Tide Percentile", default=5.0, type=float, help="Lower percentile to keep (0-100).")
    tide_filter_group.add_argument("--tide_upper_percentile", metavar="Upper Tide Percentile", default=95.0, type=float, help="Upper percentile to keep (0-100).")

    # EPSG override
    epsg_group = parser.add_argument_group("EPSG")
    epsg_group.add_argument("--epsg", metavar="EPSG Code", type=int, help="Manual EPSG override. Leave blank to auto-detect from AOI.")

    # Transect geometry controls (advanced).
    tran_group = parser.add_argument_group("Advanced Transect Settings")
    tran_group.add_argument("--transect_spacing", metavar="Transect Spacing", default=100.0, type=float, help="Spacing between transects (m).")
    tran_group.add_argument("--transect_length", metavar="Transect Length", default=200.0, type=float, help="Transect total length (m).")
    tran_group.add_argument("--transect_offset_ratio", metavar="Transect Offset Ratio", default=0.75, type=float, help="Fraction seaward vs landward (0-1).")
    tran_group.add_argument("--transect_skip_threshold", metavar="Transect Skip Threshold", default=300.0, type=float, help="Skip shoreline segments shorter than this (m).")
    add_analysis_arguments(parser, tran_group)

    # Additional download filters (advanced)
    download_group = parser.add_argument_group("Advanced Download Filters", description="Per-site imagery download filters for the pipeline engine.")
    download_group.add_argument("--months", metavar="Months to Include", nargs="+", type=str, help="Include only images taken in these months (1-12), separated by spaces or commas.")
    download_group.add_argument("--excluded_epsg_codes", metavar="Excluded EPSG Codes", nargs="+", type=str, help="Exclude images with these EPSG codes, separated by comma.")
    download_group.add_argument("--landsat_wrs", metavar="Landsat WRS Path/Row", type=str, help="Specify a Landsat tile (WRS path/row).")
    download_group.add_argument("--s2_tile", metavar="Sentinel-2 Tile", type=str, help="Specify a Sentinel-2 tile (e.g., 09UVA).")
    download_group.add_argument("--skip_l7_slc", metavar="Skip Landsat 7 SLC", action="store_true", help="Skip Landsat 7 images after Scan-Line-Correction failure.")

    # Shoreline Extraction Settings (advanced)
    shoreline_group = parser.add_argument_group("Advanced Shoreline Settings", description="Per-site shoreline extraction settings for the pipeline engine.")
    shoreline_group.add_argument("--cloud_mask_issue", metavar="Cloud Mask Issue", action="store_true", help="Set this if sand pixels are masked (in black) on many images.")
    shoreline_group.add_argument("--pan_off", metavar="Disable Pansharpening", action="store_true", help="Disable pansharpening for Landsat 7/8/9 imagery.")
    shoreline_group.add_argument("--s2cloudless_prob", metavar="S2 Cloud Probability Threshold", default=60, type=int, help="Threshold to identify cloud pixels in the s2cloudless probability mask (0-100).")
    shoreline_group.add_argument("--cloud_thresh", metavar="Cloud Coverage Threshold", default=0.5, type=float, help="Percentage of image that can be covered by cloud (0-1).")
    shoreline_group.add_argument("--dist_clouds", metavar="Cloud Buffer Distance", default=30, type=float, help="Distance in metres defining a buffer around cloudy pixels where the shoreline cannot be mapped.")
    shoreline_group.add_argument("--min_length_sl", metavar="Minimum Shoreline Length", default=500, type=float, help="Minimum length of shoreline perimeter to be kept (in meters).")
    shoreline_group.add_argument("--max_dist_ref", metavar="Maximum Distance from Reference Shoreline", default=250, type=float, help="Maximum distance from the reference shoreline in meters.")
    shoreline_group.add_argument("--check_detection", metavar="Check Shoreline Detection", action="store_true", help="Enable to check shoreline detection.")
    shoreline_group.add_argument("--adjust_detection", metavar="Adjust Shoreline Detection", action="store_true", help="Enable to adjust shoreline detection.")
    shoreline_group.add_argument("--min_beach_area", metavar="Minimum Beach Area", default=1000, type=float, help="Minimum beach area in square meters to consider for analysis.")
    shoreline_group.add_argument("--sand_color", metavar="Sand Color Classification", choices=["default", "latest", "dark", "bright"], default="default", help="Classification model for sand color: 'default', 'latest', 'dark' (for grey/black sand beaches) or 'bright' (for white sand beaches).")
    shoreline_group.add_argument("--plot_mndwi", metavar="Plot MNDWI", action="store_true", help="Enable to plot histograms of MNDWI values for each image.")
    shoreline_group.add_argument("--save_detection_plots", metavar="Save Detection Plots", action="store_true", gooey_options={"initial_value": True}, help="Enable to save detection plots (RGB, pixel classification, MNDWI, and extracted shoreline).")
    shoreline_group.add_argument("--plot_cloud_cover", metavar="Plot Cloud Cover", action="store_true", gooey_options={"initial_value": True}, help="Enable to plot histogram of cloud cover percentages of each image.")
    shoreline_group.add_argument("--save_sat_rgb", metavar="Save Satellite RGB", action="store_true", help="Enable to save satellite RGB images (must be True if plot_sat).")

    return parser


def run_setup(args) -> None:
    """Create sites and optionally run analysis from the submitted form."""
    from cli.gui_download import build_download_settings

    date_str = datetime.now().strftime("%Y%m%d")

    try:
        _validate_numeric(args)
        analysis_settings = build_analysis_settings(args)
        analysis_settings["shoreline_settings"] = build_shoreline_settings(args)
        download_settings = build_download_settings(args)
    except Exception as exc:  # noqa: BLE001
        print(f"Validation error: {exc}")
        return

    base_dir = Path(args.base_dir).expanduser().resolve()
    base_dir.mkdir(parents=True, exist_ok=True)

    # shoreline handling
    shoreline_path = Path(args.shoreline).expanduser().resolve()
    if not shoreline_path.exists():
        print(f"Shoreline file not found: {shoreline_path}")
        return

    try:
        import geopandas as gpd

        shoreline_gdf = gpd.read_file(shoreline_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to read shoreline: {exc}")
        return

    # Tide correction method
    if args.tide_method == "fes" and not args.fes_config:
        raise ValueError("Tide method FES is selected. Please select a FES config file")
    if args.tide_method == "csv" and not args.tide_csv:
        raise ValueError("Tide method CSV is selected. Please select a CSV tide file")

    # AOI input handling
    if not args.aois:
        print("Please select one or more AOI files")
        return
    aoi_paths = _split_paths(args.aois)

    if len(aoi_paths) == 1: sitenames = [args.sitename]
    else: sitenames = [f"{date_str}_{args.sitename}__{Path(i).stem}" for i in aoi_paths] # subfolders like '20260415_Vancouver__U_UTM10_0364'

    tide_config = _build_tide_config(args)
    tran_opts = {
        "spacing": float(args.transect_spacing),
        "length": float(args.transect_length),
        "offset_ratio": float(args.transect_offset_ratio),
        "skip_threshold": float(args.transect_skip_threshold),
    }

    init_results, init_failures = init_sites(
        aoi_paths, sitenames, args.epsg, shoreline_gdf, tide_config, base_dir, tran_opts,
        engine=args.engine, analysis_settings=analysis_settings, download_settings=download_settings,
    )
    print("\nInitialization complete.")
    print(f"Successful: {len(init_results)}")
    print(f"Failed    : {len(init_failures)}")
    if len(aoi_paths) > 1: write_initialization_report(init_results, init_failures, base_dir, args.sitename)

    if args.run_now:
        print("\nStarting analysis...")
        
        run_results, run_failures = run_sites(init_results, args)
        print("\nRuns Complete")
        print(f"Successful: {len(run_results)}")
        print(f"Failed    : {len(run_failures)}")
        if len(aoi_paths) > 1: write_run_report(run_results, run_failures, base_dir, args.sitename)
        
        # tell gui a run failed
        if len(run_failures) > 0:
            exit(1)


def build_gui_spec(parser):
    from gooey.python_bindings.config_generator import create_from_parser

    return create_from_parser(
        parser, __file__,
        program_name="CoastSat Site Setup",
        default_size=(800, 720),
        clear_before_run=True,
        show_restart_button=False,
        image_dir=str(IMAGE_DIR),
        language="english",
        language_dir=str(ROOT_DIR / "assets" / "gooey_languages"),
        navigation="TABBED",
        tabbed_groups=True,
        progress_regex=r"^PROGRESS: (?P<pct>\d+)%",
        progress_expr="pct",
    )


def main() -> None:
    parser = build_parser()
    arguments = sys.argv[1:]
    if "--ignore-gooey" in arguments:
        # Gooey submits the form to a separate, headless worker process.
        run_setup(parser.parse_args([arg for arg in arguments if arg != "--ignore-gooey"]))
    else:
        from cli.gui_presets import run_settings_gui

        run_settings_gui(build_gui_spec(parser))


if __name__ == "__main__":
    main()
