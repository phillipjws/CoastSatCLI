# Per-site transect and beach slope settings

The setup GUI adds analysis controls to **Advanced Transect Settings**, plus
**Outlier Filtering** and **Beach Slope** tabs. These controls apply to the
**pipeline** engine. Geometry controls still generate the transects during setup
for either engine. The legacy scripts retain their own analysis defaults.

Setup writes the following top-level keys into every generated site's
`settings.json`, including batch sites:

```json
{
    "transect_settings": {
        "along_dist": 35,
        "past_dist": 300,
        "min_chainage": -150,
        "min_points": 3,
        "max_std": 15,
        "max_range": 30,
        "CASS": true,
        "clustering_threshold": 20,
        "transects_to_plot": [],
        "plot_sat": false,
        "plot_rejection_counts": true
    },
    "outlier_settings": {
        "max_cross_change": 40,
        "otsu_threshold": [-0.5, 0],
        "plot_fig": true
    },
    "slope_estimation_date_range": ["2020-01-01", "2025-01-01"],
    "tide_timestep": 900,
    "default_slope": 0.1,
    "slope_settings": {
        "plot_fig": true,
        "slope_min": 0.005,
        "slope_max": 0.4,
        "delta_slope": 0.005,
        "n0": 50,
        "freq_cutoff": 3.858024691358025e-7,
        "delta_f": 1e-8,
        "prc_conf": 0.05,
        "n_days": 8
    }
}
```

Partial dictionaries are supported when editing an existing site. Omitted
values inherit `Parameters` defaults. The runner reads these keys directly
from the original JSON before stages run, including checkpoint reruns. It
validates values and gives each run independent copies of the mutable settings.
GUI validation happens before creating site folders.

`plot_sat` also enables `shoreline_settings.save_sat_rgb` in that run, so selected
CASS diagnostic plots have basemap data. Choose transect names explicitly to
produce those plots. `plot_entire_shoreline` and `plot_1d` are absent from the GUI
because the active CASS_V2 path does not consume them.

The Beach Slope tab applies to FES estimation. CSV tide mode continues to use
`inputs.beach_slope`, configured on **Tidal Correction**. Beach slopes are in
m/m, frequencies in Hz, and the tide timestep in seconds. `prc_conf` is an
energy tolerance, not a statistical confidence level.

The slope date window includes the start and excludes the end. It now filters
acquisitions using the same chosen window as continuous tide computation. A
window containing no acquisitions raises a clear error instead of silently
using acquisitions from outside it. If tide/mission filtering removes all
acquisitions, the existing fallback to observations within the window remains.
Skipping slope plots suppresses all four figure types while keeping estimation.
If there is insufficient data to determine a tidal frequency band, estimation
uses the configured fallback slope for each transect.
