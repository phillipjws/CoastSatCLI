"""Validated per-site analysis overrides, shared by GUI setup and pipeline runs."""

from copy import deepcopy
from datetime import datetime
import math

import pytz

from .parameters import Parameters


SITE_PARAMETER_KEYS = (
    "shoreline_settings", "transect_settings", "outlier_settings", "slope_settings",
    "slope_estimation_date_range", "tide_timestep", "default_slope",
)


def _number(value, name, minimum=None, strict=False, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if integer and not isinstance(value, int):
        raise ValueError(f"{name} must be an integer.")
    if minimum is not None and (value < minimum or (strict and value == minimum)):
        relation = ">" if strict else ">="
        raise ValueError(f"{name} must be {relation} {minimum}.")


def resolve_site_parameters(config, defaults=None):
    """Merge partial JSON overrides without changing shared parameter defaults.

    Read the original site JSON on every run, including checkpoint reruns. Older
    sites without these keys retain the values in parameters.py.
    """
    if not isinstance(config, dict):
        raise ValueError("Site settings must be a JSON object.")
    params = deepcopy(defaults if defaults is not None else Parameters())
    # Parameters currently stores mutable defaults as class attributes.
    for name in dir(params):
        if name.startswith("_"):
            continue
        value = getattr(params, name)
        if isinstance(value, (dict, list)):
            setattr(params, name, deepcopy(value))

    for name in ("shoreline_settings", "transect_settings", "outlier_settings", "slope_settings"):
        overrides = config.get(name, {})
        if not isinstance(overrides, dict):
            raise ValueError(f"{name} must be a JSON object.")
        target = getattr(params, name)
        unknown = overrides.keys() - target.keys()
        if unknown:
            raise ValueError(f"Unknown {name} parameter(s): {', '.join(sorted(unknown))}")
        target.update(deepcopy(overrides))
        for key, value in target.items():
            if isinstance(getattr(Parameters, name).get(key), bool) and not isinstance(value, bool):
                raise ValueError(f"{name}.{key} must be true or false.")

    shoreline = params.shoreline_settings
    _number(shoreline["s2cloudless_prob"], "shoreline_settings.s2cloudless_prob", 0, integer=True)
    if shoreline["s2cloudless_prob"] > 100:
        raise ValueError("S2 cloud probability threshold must be between 0 and 100.")
    _number(shoreline["cloud_thresh"], "shoreline_settings.cloud_thresh", 0)
    if shoreline["cloud_thresh"] > 1:
        raise ValueError("Cloud coverage threshold must be between 0 and 1.")
    _number(shoreline["dist_clouds"], "shoreline_settings.dist_clouds", 0)
    for key in ("min_length_sl", "max_dist_ref", "min_beach_area"):
        _number(shoreline[key], f"shoreline_settings.{key}", 0, strict=True)
    if shoreline["sand_color"] not in ("default", "latest", "dark", "bright"):
        raise ValueError("Sand color must be default, latest, dark, or bright.")

    tran = params.transect_settings
    for key in ("along_dist", "clustering_threshold"):
        _number(tran[key], f"transect_settings.{key}", 0, strict=True)
    for key in ("past_dist", "max_std", "max_range"):
        _number(tran[key], f"transect_settings.{key}", 0)
    _number(tran["min_chainage"], "transect_settings.min_chainage")
    _number(tran["min_points"], "transect_settings.min_points", 1, integer=True)
    names = tran["transects_to_plot"]
    if not isinstance(names, list) or any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("transect_settings.transects_to_plot must be a list of transect names.")
    if tran["plot_sat"]:
        params.shoreline_settings["save_sat_rgb"] = True

    outliers = params.outlier_settings
    _number(outliers["max_cross_change"], "outlier_settings.max_cross_change", 0, strict=True)
    thresholds = outliers["otsu_threshold"]
    if not isinstance(thresholds, list) or len(thresholds) != 2:
        raise ValueError("outlier_settings.otsu_threshold must contain a lower and upper bound.")
    for value in thresholds:
        _number(value, "outlier_settings.otsu_threshold", -1)
    if thresholds[0] > thresholds[1] or thresholds[1] > 1:
        raise ValueError("Outlier Otsu bounds must satisfy -1 <= lower <= upper <= 1.")

    slopes = params.slope_settings
    for key in ("slope_min", "slope_max", "delta_slope", "freq_cutoff", "delta_f", "n_days"):
        _number(slopes[key], f"slope_settings.{key}", 0, strict=True)
    _number(slopes["n0"], "slope_settings.n0", 1, integer=True)
    _number(slopes["prc_conf"], "slope_settings.prc_conf", 0)
    if slopes["prc_conf"] > 1:
        raise ValueError("slope_settings.prc_conf must be between 0 and 1.")
    if slopes["slope_min"] >= slopes["slope_max"]:
        raise ValueError("Minimum beach slope must be less than maximum beach slope.")
    if slopes["delta_slope"] > slopes["slope_max"] - slopes["slope_min"]:
        raise ValueError("Beach slope step must not exceed the slope search range.")
    maximum_frequency = 1 / (2 * slopes["n_days"] * 86400)
    if slopes["freq_cutoff"] >= maximum_frequency:
        raise ValueError("Slope frequency cutoff must be below the maximum frequency set by n_days.")
    if slopes["delta_f"] >= maximum_frequency - slopes["freq_cutoff"]:
        raise ValueError("Tidal peak half-width must fit between the frequency cutoff and maximum frequency.")

    for name in ("tide_timestep", "default_slope"):
        value = config.get(name, getattr(params, name))
        _number(value, name, 0, strict=True)
        setattr(params, name, value)
    if "slope_estimation_date_range" in config:
        dates = config["slope_estimation_date_range"]
        if not isinstance(dates, list) or len(dates) != 2:
            raise ValueError("slope_estimation_date_range must contain two YYYY-MM-DD dates.")
        parsed = []
        for value in dates:
            try:
                parsed_date = datetime.strptime(value, "%Y-%m-%d")
                if parsed_date.strftime("%Y-%m-%d") != value:
                    raise ValueError
            except (TypeError, ValueError):
                raise ValueError("Slope estimation dates must use YYYY-MM-DD format.") from None
            parsed.append(pytz.utc.localize(parsed_date))
        params.slope_estimation_date_range = parsed
    if params.slope_estimation_date_range[0] >= params.slope_estimation_date_range[1]:
        raise ValueError("Slope estimation start date must be before the end date.")
    return params
