"""Convert setup form choices into per-site pipeline download settings."""

from coastsat_pipeline.download_settings import resolve_download_settings
from coastsat_pipeline.parameters import Parameters


def _split_values(raw):
    if raw is None:
        return []
    values = raw if isinstance(raw, (list, tuple)) else [raw]
    return [item for value in values for item in str(value).replace(",", " ").split()]


def build_download_settings(args):
    settings = {
        "dates": [args.start_date, args.end_date],
        "sat_list": list(args.sat_list),
        "skip_L7_SLC": args.skip_l7_slc,
    }
    months = _split_values(args.months)
    if months:
        try:
            settings["months"] = [int(month) for month in months]
        except ValueError:
            raise ValueError("Months must be integers from 1 to 12, separated by spaces or commas.") from None
    codes = _split_values(args.excluded_epsg_codes)
    if codes:
        settings["excluded_epsg_codes"] = codes
    for argument, key in (("landsat_wrs", "LandsatWRS"), ("s2_tile", "S2tile")):
        value = getattr(args, argument)
        if value and value.strip():
            settings[key] = value.strip()
    resolve_download_settings(Parameters.download_filters, settings)
    return settings
