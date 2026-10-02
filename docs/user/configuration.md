# Configuration Reference

Each CoastSatCLI project is driven by a `settings.json` file created during `init`. This document explains every field, default behavior, and how downstream scripts use the values.

---

## 1. File Layout

`settings.json` lives at the root of each site folder:
```
<base>/<sitename>/
├─ inputs/
│  ├─ aoi/
│  ├─ shoreline/
│  ├─ reference/
│  └─ transects/
├─ outputs/
└─ settings.json
```

Relative paths inside the file are resolved against the site directory when `coastsatcli.py run` executes.

---

## 2. Top-Level Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `inputs` | object | ✅ | Paths to AOI/reference data plus sitename metadata. |
| `output_dir` | string | ✅ | Relative path to the folder where analysis outputs are written (typically `outputs`). |
| `output_epsg` | integer | ✅ | EPSG code used for reprojection of transects and exported products. |
| `tide_filter` | object | optional | Percentile filter applied during tide correction. |
| `engine` | string | optional | `pipeline` or `legacy`, saved during GUI/CLI initialization. Later CLI runs use this unless `--engine` overrides it. Older files without this field use `legacy`. |
| `notes` | string | optional | Free-form field for analysts to document context (ignored by scripts but useful for provenance). |

Unknown fields are ignored by the analysis scripts but should be grouped under a dedicated namespace (e.g., `"experimental"`) to avoid collisions.

The initialization GUI saves its engine dropdown selection even when "Run now" is unchecked. For an existing site created before this setting was saved, add `"engine": "pipeline"` at the top level to use the pipeline by default. An explicit `--engine` overrides the selection for that run without changing the saved setting. The site rerun GUI's `auto` selection uses the saved engine.

---

## 3. `inputs` Block

```json
"inputs": {
  "sitename": "tuk",
  "aoi_path": "inputs/aoi/tuk_aoi.kml",
  "shoreline_path": "inputs/shoreline/CANCOAST.geojson",
  "reference_shoreline": "inputs/reference/tuk_ref.geojson",
  "transects": "inputs/transects/tuk_transects.geojson",
  "fes_config": "C:/data/fes2022/fes2022.yaml",
  "tide_csv_path": null,
  "reference_elevation": null,
  "beach_slope": null
}
```

| Field | Description | Notes |
| --- | --- | --- |
| `sitename` | Identifier used throughout logs and output filenames. | Keep lowercase/alphanumeric to avoid path issues. |
| `aoi_path` | AOI polygon (KML/GeoJSON). | Generated during init; should remain relative to site root. |
| `shoreline_path` | (Optional) Original shoreline dataset stored for reference. | Can be omitted if the dataset is large; only the reference shoreline is required downstream. |
| `reference_shoreline` | Clipped shoreline aligned with AOI. | Used to seed transect generation. |
| `transects` | Transect GeoJSON produced by init or regeneration. | Downstream scripts rely on attributes such as `TransectID`. |
| `fes_config` | Absolute path to FES2022 YAML for tide mode. | Required when using `fes` tide correction. |
| `tide_csv_path` | Alternate tide input when using CSV mode. | Mutually exclusive with `fes_config`. |
| `reference_elevation` | Datum elevation associated with the CSV tide series. | Only used in CSV mode. |
| `beach_slope` | Optional override when slope estimates are known beforehand. | Leave `null` to have the pipeline estimate slopes. |

> **Recommendation:** avoid editing `settings.json` manually. Use `coastsatcli.py site-rerun` to regenerate transects or update tide settings so the CLI keeps paths consistent.

---

## 4. Tide Filter Object

```json
"tide_filter": {
  "lower_percentile": 5.0,
  "upper_percentile": 95.0
}
```

- Percentiles define the range of tide levels to **keep**. Measurements outside the range are removed before plotting, slope estimation, and CSV export.
- Values must satisfy `0 <= lower < upper <= 100`.
- Filter statistics (thresholds, number of removals) are written to the logs and exported in the transect GeoJSON attributes for transparency.

If no `tide_filter` is provided, all detections are retained.

---

## 5. Derived / Runtime Fields

Some values are added during the run command for internal use:

| Field | Added By | Purpose |
| --- | --- | --- |
| `settings["resolved_paths"]` (in-memory) | `Complete_Analysis.load_settings` | Maps relative paths to absolute ones for downstream modules; not persisted. |
| `settings["tide_filter_stats"]` | Tide correction stage | Captures computed thresholds and removal counts; persisted alongside outputs. |

These fields should not be set manually. They are mentioned here so analysts understand where additional metadata originates.

---

## 6. Example Variations

- **CSV Tide Mode**: Replace `fes_config` with `tide_csv_path`, `reference_elevation`, and optional `beach_slope`. Useful when working with local tide gauges or custom models.
- **No-Tide Workflow**: Omit both `fes_config` and `tide_filter`. The CLI will automatically run `Complete_Analysis_No_Tide.py`.
- **Custom Date Ranges / Satellites**: Currently hard-coded in `Complete_Analysis.py`. A future ADR will cover exposing these as config fields; until then, edit the script carefully if you need non-default ranges.

Keep sanitized configuration examples (CSV, no-tide, batch) under a shared `docs/examples/` folder so new analysts can inspect working templates.
