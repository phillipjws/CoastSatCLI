"""GUI controls and serialization for pipeline analysis parameters."""

from datetime import date

from coastsat_pipeline.parameters import Parameters
from coastsat_pipeline.site_parameters import resolve_site_parameters


def add_analysis_arguments(parser, tran_group):
    tran = Parameters.transect_settings
    for key, label, help_text in (
        ("along_dist", "Intersection Corridor (m)", "Maximum perpendicular distance of shoreline points from a transect."),
        ("past_dist", "Beyond Transect End (m)", "Accept shoreline points this far past the seaward end."),
        ("min_chainage", "Minimum Chainage (m)", "Furthest accepted position relative to the origin; negative is landward."),
        ("min_points", "Minimum Intersection Points", "Minimum number of shoreline points needed for an intersection."),
        ("max_std", "Maximum Intersection Std Dev (m)", "Reject intersections whose standard deviation exceeds this value."),
        ("max_range", "Maximum Intersection Range (m)", "Reject intersections whose spread exceeds this value."),
        ("clustering_threshold", "CASS Cluster Gap (m)", "Gap between adjacent intersections needed to start a new cluster."),
    ):
        tran_group.add_argument(f"--{key}", metavar=label, default=tran[key],
                                type=int if key == "min_points" else float, help=help_text + " Pipeline engine.")
    tran_group.add_argument("--disable_cass", metavar="Disable CASS Selection", action="store_true",
                            help="Use the basic intersection selection instead of CASS. Pipeline engine.")
    tran_group.add_argument("--transects_to_plot", metavar="Transects to Plot", default="",
                            help="Comma-separated names, e.g. transect_1,transect_2. Requires CASS. Pipeline engine.")
    tran_group.add_argument("--plot_sat", metavar="Satellite Basemap", action="store_true",
                            help="Add imagery to selected CASS transect plots; also save RGB data during extraction. Pipeline engine.")
    tran_group.add_argument("--skip_rejection_plots", metavar="Skip Intersection Rejection Plots", action="store_true",
                            help="Skip rejection-count plots produced by CASS. Pipeline engine.")

    outlier_group = parser.add_argument_group("Outlier Filtering", description="Pipeline time-series filtering after transect intersections.")
    outliers = Parameters.outlier_settings
    outlier_group.add_argument("--max_cross_change", metavar="Maximum Cross-shore Change (m)", type=float,
                               default=outliers["max_cross_change"], help="Maximum change allowed between consecutive observations.")
    outlier_group.add_argument("--otsu_min", metavar="Minimum Otsu Threshold", type=float,
                               default=outliers["otsu_threshold"][0], help="Reject observations below this recorded MNDWI threshold (-1 to 1).")
    outlier_group.add_argument("--otsu_max", metavar="Maximum Otsu Threshold", type=float,
                               default=outliers["otsu_threshold"][1], help="Reject observations above this recorded MNDWI threshold (-1 to 1).")
    outlier_group.add_argument("--skip_outlier_plots", metavar="Skip Outlier Filtering Plots", action="store_true",
                               help="Skip time-series plots before and after outlier rejection.")

    slope_group = parser.add_argument_group("Beach Slope", description="Pipeline FES slope estimation. CSV mode uses the slope on the Tidal Correction tab.")
    slope_group.add_argument("--slope_start_date", metavar="Slope Start Date", widget="DateChooser",
                             default="1999-01-01", help="Start of slope estimation window (included).")
    slope_group.add_argument("--slope_end_date", metavar="Slope End Date", widget="DateChooser",
                             default=date.today().strftime("%Y-%m-%d"), help="End of slope estimation window (excluded).")
    slope_group.add_argument("--tide_timestep", metavar="Tide Timestep (seconds)", type=float,
                             default=Parameters.tide_timestep, help="Interval for computing the continuous FES tide series.")
    slope_group.add_argument("--default_slope", metavar="Fallback Beach Slope (m/m)", type=float,
                             default=Parameters.default_slope, help="Slope used when estimation fails for a transect.")
    slopes = Parameters.slope_settings
    for key, label, help_text in (
        ("slope_min", "Minimum Beach Slope (m/m)", "Smallest beach slope to test."),
        ("slope_max", "Maximum Beach Slope (m/m)", "Largest beach slope to test."),
        ("delta_slope", "Beach Slope Step (m/m)", "Step between candidate beach slopes."),
        ("n0", "Frequency Grid Oversampling", "Advanced: spectral frequency grid oversampling factor."),
        ("freq_cutoff", "Frequency Cutoff (Hz)", "Advanced: ignore lower frequencies when locating the tidal peak."),
        ("delta_f", "Tidal Peak Half-width (Hz)", "Advanced: frequency band on each side of the tidal peak."),
        ("prc_conf", "Energy Tolerance (0-1)", "Advanced: relative energy tolerance for slope uncertainty; 0.05 means 5%."),
        ("n_days", "Sampling Interval (days)", "Advanced: sets the maximum spectral frequency to 1 / (2 * interval)."),
    ):
        slope_group.add_argument(f"--{key}", metavar=label, default=slopes[key],
                                 type=int if key == "n0" else float, help=help_text)
    slope_group.add_argument("--skip_slope_plots", metavar="Skip Slope Estimation Plots", action="store_true",
                             help="Skip timestep, tide spectrum, energy curve, and slope spectrum figures.")


def build_analysis_settings(args):
    """Build JSON-compatible site values and reject invalid choices before setup."""
    settings = {
        "transect_settings": {
            key: getattr(args, key) for key in (
                "along_dist", "past_dist", "min_chainage", "min_points", "max_std", "max_range", "clustering_threshold"
            )
        },
        "outlier_settings": {
            "max_cross_change": args.max_cross_change,
            "otsu_threshold": [args.otsu_min, args.otsu_max],
            "plot_fig": not args.skip_outlier_plots,
        },
        "slope_settings": {
            key: getattr(args, key) for key in (
                "slope_min", "slope_max", "delta_slope", "n0", "freq_cutoff", "delta_f", "prc_conf", "n_days"
            )
        },
        "slope_estimation_date_range": [args.slope_start_date, args.slope_end_date],
        "tide_timestep": args.tide_timestep,
        "default_slope": args.default_slope,
    }
    settings["transect_settings"].update(
        CASS=not args.disable_cass,
        transects_to_plot=[name.strip() for name in args.transects_to_plot.split(",") if name.strip()],
        plot_sat=args.plot_sat,
        plot_rejection_counts=not args.skip_rejection_plots,
    )
    settings["slope_settings"]["plot_fig"] = not args.skip_slope_plots
    resolve_site_parameters(settings)
    return settings


def build_shoreline_settings(args):
    settings = {key: getattr(args, key) for key in Parameters.shoreline_settings}
    resolve_site_parameters({"shoreline_settings": settings})
    return settings
