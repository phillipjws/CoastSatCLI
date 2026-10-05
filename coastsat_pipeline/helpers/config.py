from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..context import TideConfig, TideFilterConfig
from ..download_settings import resolve_download_settings
from coastsat import SDS_tools


def build_settings(config_path: Path, download_filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Load site settings and resolve download overrides over pipeline defaults.
    """
    config = _load_config_dict(config_path)
    selected = resolve_download_settings(download_filters, config.pop("download_settings", {}))
    config.update(selected)
    tide_cfg = _build_tide_config(config)
    config["tide_cfg"] = tide_cfg
    return config


def _load_config_dict(config_path: Path) -> Dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    with open(config_path, "r") as f:
        config = json.load(f)
    base_dir = config_path.parent
    if not isinstance(config, dict):
        raise ValueError("settings.json must contain an object.")
    if not isinstance(config.get("download_settings", {}), dict):
        raise ValueError("download_settings must be an object.")

    if "output_epsg" not in config:
        raise KeyError("settings.json must include an 'output_epsg' entry.")


    inputs_config = config.get("inputs", {})
    for key in ("aoi_path", "reference_shoreline", "transects"):
        if key in inputs_config:
            inputs_config[key] = str((base_dir / inputs_config[key]).resolve())


    new_config = {"download_settings": config.get("download_settings", {})}
    for key in ("fes_config", "tide_csv_path"):
        if inputs_config.get(key):
            inputs_config[key] = str((base_dir / Path(inputs_config[key]).expanduser()).resolve())

    if "output_dir" in config:
        new_config["filepath"] = str((base_dir / config["output_dir"]).resolve())

    tide_filter_cfg = config.get("tide_filter")
    if tide_filter_cfg is not None:
        lower, upper = _normalize_tide_filter(tide_filter_cfg)
        new_config["tide_filter"] = {"lower_percentile": lower, "upper_percentile": upper}

    polygon = SDS_tools.polygon_from_kml(inputs_config["aoi_path"])
    polygon = SDS_tools.smallest_rectangle(polygon)
    
    new_config.update({
        "polygon": polygon,
        "sitename": inputs_config["sitename"],
        "reference_geojson": inputs_config["reference_shoreline"],
        "transect_geojson": inputs_config["transects"],
        "fes_config": inputs_config.get("fes_config"),
        "tide_csv_path": inputs_config.get("tide_csv_path"),
        "output_epsg": config["output_epsg"]
    })
    for key in ("reference_elevation", "beach_slope"):
        if inputs_config.get(key) is not None:
            value = inputs_config[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a finite number.")
            if not math.isfinite(value) or (key == "beach_slope" and value <= 0):
                raise ValueError(f"{key} must be finite" + (" and positive." if key == "beach_slope" else "."))
            new_config[key] = value

    return new_config


def load_settings_from_cli_config(config_path: Path) -> Dict[str, Any]:
    """
    Legacy compatibility helper used by older CLI flows and tests.

    Returns the normalized dict representation (with resolved paths and tide filter).
    """
    return _load_config_dict(Path(config_path))


def _build_tide_config(config: Dict[str, Any]) -> TideConfig:
    inputs = config.get("inputs", config)
    tide_filter_data = config.get("tide_filter")
    tide_filter = None
    if tide_filter_data:
        tide_filter = TideFilterConfig(
            lower_percentile=float(tide_filter_data["lower_percentile"]),
            upper_percentile=float(tide_filter_data["upper_percentile"]),
        )

    if inputs.get("fes_config"):
        mode = "fes"
    elif inputs.get("tide_csv_path"):
        mode = "csv"
    else:
        mode = "none"

    return TideConfig(
        mode=mode,
        fes_config=Path(inputs["fes_config"]).expanduser() if inputs.get("fes_config") else None,
        tide_csv_path=Path(inputs["tide_csv_path"]).expanduser() if inputs.get("tide_csv_path") else None,
        reference_elevation=inputs.get("reference_elevation"),
        beach_slope=inputs.get("beach_slope"),
        tide_filter=tide_filter,
    )


def _normalize_tide_filter(tide_filter_cfg: Any) -> Tuple[float, float]:
    if isinstance(tide_filter_cfg, (list, tuple)):
        if len(tide_filter_cfg) != 2:
            raise ValueError("tide_filter list must contain [lower_percentile, upper_percentile].")
        lower, upper = tide_filter_cfg
    elif isinstance(tide_filter_cfg, dict):
        lower = tide_filter_cfg.get("lower_percentile")
        upper = tide_filter_cfg.get("upper_percentile")
    else:
        raise TypeError("tide_filter must be provided as a dict or two-item list/tuple.")

    if lower is None or upper is None:
        raise ValueError("tide_filter requires both lower_percentile and upper_percentile values.")

    lower = float(lower)
    upper = float(upper)
    if not (0 <= lower < upper <= 100):
        raise ValueError("tide_filter percentiles must satisfy 0 <= lower < upper <= 100.")
    return lower, upper
