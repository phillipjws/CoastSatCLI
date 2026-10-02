# CLI User Guide

This guide walks analysts through the CoastSatCLI workflow from verifying installation to reviewing outputs. It assumes you already followed the installation steps in the root README (Miniforge/Mamba environment + GEE authentication).

---

## 1. Getting Started

### 1.1 Verify the Environment
```bash
conda activate coastsat
python --version
gcloud auth list
```
Confirm the Python version is 3.11 (or compatible) and that Earth Engine credentials are active. If `gcloud auth list` shows no active account, re-run `gcloud auth application-default login`.

### 1.2 Check CLI Availability
```bash
python cli/coastsatcli.py --help
```
You should see Typer-generated help text listing the `init`, `run`, `site-rerun`, and `show` commands. If the command fails, revisit your environment activation or repository path.

---

## 2. Initializing a Site (`init`)

### 2.1 Required Inputs
- **AOI polygon** (KML/GeoJSON) defining the coastline segment.
- **Reference shoreline** covering a larger extent (GeoJSON or SHP).
- **Transect configuration** (spacing, length, offset) — defaults provided but confirm with your analyst lead.
- **Tide configuration**:
  - `fes` mode: path to `fes2022.yaml`.
  - `csv` mode: tide CSV, reference elevation, and optional slope.

### 2.2 Launch the Wizard
```bash
python cli/coastsatcli.py init
```

The CLI (or dialogs on Windows) guides you through:
1. Selecting the AOI file and sitename.
2. Selecting the shoreline dataset to clip and form the reference shoreline.
3. Choosing transect parameters (spacing, length, skip threshold).
4. Supplying tide settings and percentile filters.
5. Picking a base directory where the project folder `<base>/<sitename>/` will be created.

> **Tip:** If you are initializing multiple AOIs from the same shoreline dataset, keep the shoreline loaded in memory using the batch subcommand (see `python cli/coastsatcli.py init --help` for advanced options).

### 2.3 Outputs
- Project structure scaffolded with `inputs/` and `outputs/`.
- `settings.json` containing relative paths and EPSG codes.
- Reference shoreline (`inputs/reference/`) and transect GeoJSON (`inputs/transects/`).

---

## 3. Running the Analysis (`run`)

### 3.1 Command
```bash
python cli/coastsatcli.py run --config path/to/<sitename>/settings.json
```

The command uses the `engine` saved in `settings.json` during setup. To override it for one run, add `--engine pipeline` or `--engine legacy`. Older settings files without an `engine` field retain the legacy default; add `"engine": "pipeline"` at the top level to make those sites use the pipeline automatically.

### 3.2 What Happens
1. Settings are validated and paths resolved.
2. CoastSat downloads imagery from GEE (if not already cached) and runs shoreline detection.
3. QC plots, GeoJSON, and CSV files are written to `outputs/`.
4. If `tide_filter` or `fes_config` is set, tide correction and percentile filtering are applied.

### 3.3 Monitoring Progress
- Logs stream to the console with markers for each pipeline stage (download, preprocess, shoreline detection, tide correction, slope estimation).
- Failures stop the pipeline and leave partial artifacts; re-running after fixing the issue will reuse cached imagery.

### 3.4 Inspect Outputs
Use the `show` command for a quick tree view:
```bash
python cli/coastsatcli.py show --config path/to/<sitename>/settings.json
```

Manually review:
- `outputs/plots/` — shoreline overlays, transect series, spectra.
- `outputs/time_series/` — CSVs for each transect/satellite.
- `outputs/debug/` (if enabled) — raw GeoJSON for QA.

---

## 4. Rerunning with Updated Inputs (`site-rerun`)

When transects, AOIs, or reference shorelines change, avoid rebuilding the project manually.

```bash
python cli/coastsatcli.py site-rerun
```

Workflow:
1. Select an existing `settings.json`.
2. Choose whether to replace the reference shoreline and/or regenerate transects (using stored parameters).
3. Optionally clear previous outputs to force a fresh analysis.
4. Automatically trigger the `run` command or exit after updating inputs.

This command preserves imagery caches but refreshes the parts you changed, improving usability and keeping provenance intact.

---

## 5. QA/QC Checklist

Before accepting a site’s results:

1. **Transect sanity** — open the generated transect GeoJSON in QGIS/ArcGIS to confirm spacing, orientation, and coverage.
2. **Shoreline overlays** — inspect plots for each satellite/epoch to ensure the classifier is tracing the true shoreline (look for clouds, snow, or mismatched transects).
3. **Tide filter summary** — check the percentile stats written to CSV/logs to confirm extremes were removed as expected.
4. **Slope confidence** — review slope spectrum plots; wide confidence intervals may signal insufficient observations.
5. **Trend CSVs** — verify there are no NaNs or obvious outliers in the exported statistics.

If anything looks off, re-run `site-rerun` to adjust inputs or tweak tide/transect parameters, then repeat the QA steps.

--- 
## 6. Standalone Tide Series Export

Need only the tide model output without running the full shoreline workflow? Use the helper script:

```bash
python cli/run_tide_model.py --config path/to/<sitename>/settings.json --output tides.csv
```

Key options:
- `--start/--end`: ISO timestamps in UTC (defaults `2013-01-01T00:00:00Z` to `2025-12-31T00:00:00Z`).
- `--step-minutes`: sample spacing (default 15 minutes).
- `--lon/--lat`: override or provide the centroid directly.
- `--aoi-path`: AOI polygon (KML/GeoJSON) so the script can determine a centroid without a config file.
- `--fes-config`: path to `fes2022.yaml` if your settings file does not include it (required when `--config` is omitted).

The script loads the FES2022 handlers, determines a valid centroid (using the AOI if available), runs `coastsat.SDS_slope.compute_tide`, and saves `timestamp_utc,tide_m` pairs to the requested CSV.

---

For troubleshooting tips and deep dives into configuration fields, refer to:
- [`docs/user/configuration.md`](configuration.md)
- [`docs/user/troubleshooting.md`](troubleshooting.md)
- [`docs/user/glossary.md`](glossary.md)
