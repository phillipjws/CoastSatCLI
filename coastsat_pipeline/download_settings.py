"""Site-level download settings, independent of GUI and geospatial imports."""

from copy import deepcopy
from datetime import date
import re

DOWNLOAD_KEYS = frozenset({
    "dates", "sat_list", "months", "excluded_epsg_codes", "LandsatWRS",
    "S2tile", "skip_L7_SLC",
})
SATELLITES = ("L5", "L7", "L8", "L9", "S2")


def resolve_download_settings(defaults: dict, overrides: dict | None = None) -> dict:
    """Merge partial site overrides over defaults without modifying either."""
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError("download_settings must be an object.")
    unknown = overrides.keys() - DOWNLOAD_KEYS
    if unknown:
        raise ValueError(f"Unknown download settings: {', '.join(sorted(unknown))}")
    settings = deepcopy(defaults)
    settings.update(deepcopy(overrides))
    dates = settings.get("dates")
    if not isinstance(dates, list) or len(dates) != 2:
        raise ValueError("dates must contain [start, end] in YYYY-MM-DD format.")
    try:
        if any(not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in dates):
            raise ValueError
        start, end = map(date.fromisoformat, dates)
    except ValueError as exc:
        raise ValueError("dates must contain valid YYYY-MM-DD dates.") from exc
    if start >= end:
        raise ValueError("Download start date must precede end date.")
    missions = settings.get("sat_list")
    if not isinstance(missions, list) or not missions or any(
        not isinstance(mission, str) or mission not in SATELLITES for mission in missions
    ):
        raise ValueError(f"sat_list must be a nonempty list drawn from {SATELLITES}.")
    if len(set(missions)) != len(missions):
        raise ValueError("sat_list must not contain duplicate missions.")
    if "months" in settings:
        months = settings["months"]
        if not isinstance(months, list) or not months or any(type(m) is not int or not 1 <= m <= 12 for m in months):
            raise ValueError("months must be a nonempty list of integers from 1 to 12.")
    if "skip_L7_SLC" in settings and type(settings["skip_L7_SLC"]) is not bool:
        raise ValueError("skip_L7_SLC must be a boolean.")
    if "excluded_epsg_codes" in settings:
        codes = settings["excluded_epsg_codes"]
        if not isinstance(codes, list) or any(
            not ((type(code) is int and code > 0) or
                 (isinstance(code, str) and code.isascii() and code.isdigit() and int(code) > 0))
            for code in codes
        ):
            raise ValueError("excluded_epsg_codes must be a list of positive EPSG numbers.")
    for key, pattern in (("LandsatWRS", r"\d{6}"), ("S2tile", r"\d{2}[A-Z]{3}")):
        if key in settings and (not isinstance(settings[key], str) or not re.fullmatch(pattern, settings[key])):
            raise ValueError(f"{key} has an invalid tile identifier.")
    return settings
