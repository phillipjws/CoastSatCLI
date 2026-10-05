# CoastSatCLI

Command-line and GUI tools for running CoastSat end to end for the Canadian Coastal Change program. The repo contains both the new stage-based pipeline (preferred) and the legacy CLI/analysis scripts for compatibility.

## Project overview
- Purpose: create consistent, reproducible shoreline change products for Canadian Areas of Interest (AOIs) with tide-aware processing.
- Modes: headless pipeline runner, GUI for the pipeline, and legacy Typer CLI backed by the original CoastSat scripts.
- Outputs: plots, GeoJSON, CSV trend artifacts, and debug assets under each site's `output_dir`.

## Setup
0) Install the basics (if new to this stack):
   - Git (CLI) download: https://git-scm.com/downloads  
     <details><summary>What it is</summary>Version control used to download this project and stay in sync (`git clone`, `git pull`).</details>
   - VS Code download: https://code.visualstudio.com/  
     <details><summary>What it is</summary>Editor with a built-in terminal for running these commands and editing configs.</details>
   - QGIS download: https://qgis.org/en/site/forusers/download.html  
     <details><summary>What it is</summary>Desktop GIS to view AOIs, shorelines, and generated transects before/after runs.</details>
   - Miniforge download: https://github.com/conda-forge/miniforge#miniforge3  
     <details><summary>What it is</summary>Conda-based environment manager for Python + geospatial deps.</details>
   - Google Cloud SDK download: https://cloud.google.com/sdk/docs/install  
     <details><summary>What it is</summary>CLI used to authenticate with Google Earth Engine via `gcloud init` (sets your account and project for downloads).</details>

   Note: if you do not have admin rights on your machine (you won't), choose the "install for me only" option in each installer. A system-wide install is not necessary to use this project.

1) Clone the repo (git):
```bash
git clone https://github.com/AriveIT/CoastSatCLI.git
cd CoastSatCLI
```

2) Create the environment (Miniforge):
```bash
conda env create -f environment.yml
conda activate coastsat
```

3) Enable Google Earth Engine (Google Cloud SDK):
```bash
gcloud init
gcloud config get-value project  # sanity-check that init set the right project
```
GEE access uses your Google Cloud credentials. `gcloud init` authenticates and sets the active account/project; the `get-value project` check confirms you are pointed at the right workspace before downloading imagery.

4) Prepare tide inputs (pick based on site type):
   - Option 1 (CSV tides, e.g., lakes/river-influenced sites): use a CSV with a time series of water levels (15/30 min or finer). Follow the format in `examples/NARRA_tides.csv`: timestamps in UTC, tide heights in metres above mean sea level.
   - Option 2 (FES2022, open-ocean sites): use the FES2022 global tide model to predict tides for your site. Two install paths:
     - Standard install: follow the official FES2022 instructions (download packages, configure paths) from the [FES release page](https://www.aviso.altimetry.fr/en/data/products/auxiliary-products/global-tide-fes/release-fes22.html) and the CoastSat guide: https://github.com/kvos/CoastSat/blob/master/doc/FES2022_setup.md.
     - Fast path (preferred if you have access to the P drive): grab the zip under `P:\CoastSat\Jan Noobs\fes set up files\`, unzip it on your machine, and place `fes2022.yaml` in the same folder. Edit the paths inside `fes2022.yaml` to match your local directory layout (see the FES docs for details). Point the tools to that local folder.
     Once installed, you can predict tides for any dates and locations worldwide.

After these steps you should be ready to run a site: you have the repo cloned, the Conda environment created, GEE configured, and tide inputs chosen (CSV for lakes/river sites, FES2022 for open ocean). Next, follow the workflows below to scaffold a site and run the pipeline.

## How to use
This repository contains my work on making CoastSat easier to run, reuse, and extend. I originally started by building a fully CLI-driven workflow that could run CoastSat end-to-end, from project setup through shoreline extraction and analysis. That early version helped me understand the pipeline deeply and served as a reliable, scriptable way to process sites.

As the project matured, I refactored the core logic into a cleaner, more modular pipeline and built a simple GUI on top of it. This newer pipeline is now the recommended way to run CoastSat, as it is more user-friendly, easier to configure, and better suited for day-to-day use by new users. The GUI provides a guided way to move through the main steps while still relying on the same underlying processing code.

Both approaches live in this repository on purpose. If you are just getting started, you should use the new pipeline and GUI by default. The original CLI workflow is kept as a reference and fallback option—it is useful for debugging, understanding how the pieces fit together, or running things manually if something unexpected comes up.

### Process at a glance
These are the essential stages the CoastSat tooling runs through for each site:
- Prepare inputs: collect AOI polygons, shoreline vectors, and tide inputs (CSV or FES2022) and scaffold a site folder with `settings.json`.
- Download and preprocess imagery: use Google Earth Engine to pull Landsat/Sentinel scenes, apply basic masking, reprojection, and stacking.
- Detect shorelines and QC: run shoreline classification, generate overlay plots, and review per-transect time series for obvious issues.
- Tide correction and transects: apply transects, compute beach slope/tide adjustments, and filter outliers where configured.
- Aggregate and export: write GeoJSON/CSV outputs, plots, and debug artifacts into the site `output_dir` for review and sharing.

### Pipeline + GUI Workflow (recommended)
1) Create `settings.json` with the init GUI:
```bash
python -m cli.gui_init
```
   - In the GUI, select a base folder and sitename(s), pick a shoreline file, choose AOI KML(s) (single or batch, generated with [geojson.io](https://geojson.io/)), pick tide method (FES config vs tide CSV with beach slope), optional tide filtering, let EPSG auto-detect or override it, and adjust transect spacing/length/offset if needed. The GUI writes `settings.json` and scaffolds the site; you can also check “run now” to start analysis immediately (choose engine `pipeline`).
   - Use the **Save Settings...** button at the top of the window (`Ctrl+S`) to save your form choices to a separate JSON file, even before completing setup. Later, use **Load Settings...** (`Ctrl+O`) to restore them and continue editing. These actions are also available in the **File** menu. Saving or opening a file does not create a site or start analysis. Saved GUI settings retain file paths, so check those paths if you move inputs or share the file. These files are separate from each site's analysis `settings.json`; see [saved GUI settings](docs/user/gui-settings.md).
2) Run the pipeline via GUI:
```bash
python -m coastsat_pipeline.gui
```
   - Pick the `settings.json` you just created and click Run.
3) Or run headless (scripted):
```bash
python - <<'PY'
from pathlib import Path
from coastsat_pipeline.cli import run_pipeline_from_config
run_pipeline_from_config(Path("path/to/settings.json"))
PY
```
4) Review outputs under the configured `output_dir` (plots, GeoJSON, CSVs).

### CLI + Scripts Workflow (fallback/reference)
```bash
python cli/CoastsatCLI.py init          # guided setup to build a site and settings.json
python cli/CoastsatCLI.py run --config path/to/settings.json
```
The init GUI saves its engine selection in each site's `settings.json`. CLI runs use that saved engine; `--engine pipeline` or `--engine legacy` overrides it for one run. Older settings files without an `engine` field use legacy behavior. Add `"engine": "pipeline"` at the top level of an older site's settings to use the new pipeline by default.

### Reruns and inspection (either path)
- Rerun with updated transects/ref shorelines: `python cli/CoastsatCLI.py site-rerun --config path/to/settings.json`.
- Summarize outputs: `python cli/CoastsatCLI.py show --config path/to/settings.json`.

### Parameters
Certain parameters are exposed during site initialization through the GUI. All other parameters are available in `coastsat_pipeline/parameters.py`. These should be read through before running a site.

### Checkpoints
At the beginning of each stage, the current context is saved in <stagename>.pkl in the checkpoints folder. The pipeline can be run at the beginning of a stage using these checkpoint files.

1) Run from specific stage
```bash
python run_from_cp.py <stagename>
```

2) Run from last started stage
```bash
python run_from_cp.py
```

## Repository map
- `coastsat_pipeline/` - stage registry, runner, GUI.
- `cli/` - legacy Typer CLI plus Gooey wrappers for init and site rerun.
- `Complete_Analysis.py`, `Complete_Analysis_No_Tide.py` - legacy runners invoked by the CLI.
- `coastsat/` - upstream CoastSat scripts used by the legacy flow.
- `classification/` - model files and training notebook.
- `docs/` - architecture, ops, user, and dev guides (see `docs/README.md`).
- `tests/` - unit tests for the pipeline and helpers.

## Testing and quality
- Fast suite: `pytest tests -q`
- For new features, add fixtures or sample `settings.json` under `docs/examples/` to keep handoff easy.

## Support and docs
- Start: `docs/README.md` (map of the docs).
- User guides and configuration reference: `docs/user/`.
- Ops runbook and environment notes: `docs/ops/`.
- Architecture and ADRs: `docs/architecture/`, `docs/adrs/`.
- Dev standards and release guidance: `docs/dev/`.

If you add or rename docs, update `docs/README.md` and cross-links here. Keep large models out of Git and note where to fetch them in `classification/`.
