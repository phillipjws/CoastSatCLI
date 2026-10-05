# Saving and opening GUI settings

Launch the site setup GUI from the activated CoastSat environment:

```bash
python -m cli.gui_init
```

The setup window loads its form dependencies first. Geospatial libraries load
after you click **Start**, and analysis libraries load when analysis is requested.
This lets you edit, save, and open settings without waiting for the processing
libraries to initialize.

The **Load Settings...** and **Save Settings...** buttons are at the top of the
setup window and remain visible across all tabs. If the GUI was already open
when it was updated, close it and launch it again to see the new controls.

Use **Save Settings...** (or **File > Save Settings...**, `Ctrl+S`) to choose where to save a JSON file.
The default filename is `gui-settings.json`. You can save an unfinished form;
required inputs and analysis parameters are validated when you click **Start**.

Use **Load Settings...** (or **File > Open Settings...**, `Ctrl+O`) to select a previously saved GUI settings
file. It restores the form across all tabs, including:

- Base directory, site name, original shoreline and AOI file selections.
- Engine, download dates, satellite missions, and advanced download filters.
- Tide method, input files, beach slope, and tide filtering.
- EPSG override and transect creation options.
- Shoreline, transect intersection, outlier, and slope settings.
- Checked and unchecked boxes, including **Run Analysis Now** and **Delete Intermediate TIFs**.

You can review and change restored choices before clicking **Start**. Saving and
opening settings do not initialize projects, download imagery, or start analysis.
The settings buttons and file actions are disabled while a setup or analysis run is in progress.

Saved GUI files keep the paths entered in the form. They do not package the input
files. If you move files or share settings with another computer, update the paths
in the GUI. Relative paths still resolve against the directory where you launch
the GUI, just as they do when entered manually.

Each project's `settings.json` remains the analysis configuration used to run an
existing site. It contains generated site inputs and does not retain every setup
choice. **Open Settings...** accepts GUI settings files created by **Save Settings...**;
to run an existing project's `settings.json`, use `python -m coastsat_pipeline.gui`.

Invalid JSON, unsupported versions, and invalid form values show an error and
leave your current form untouched. Settings files from an earlier form version
use initial defaults for any newly added fields; unrecognized fields are rejected.
