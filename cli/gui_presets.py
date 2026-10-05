"""Save and restore the setup form without executing the setup workflow.

Only raw control values are persisted, never Gooey build specs or commands.
The Gooey widget API is isolated here because its Listbox setter adds selections
and its Dropdown setter cannot restore an empty selection.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


PRESET_FORMAT = "coastsat-gui-settings"
PRESET_VERSION = 1


class FormSettings:
    """Persist the controls of a Gooey ConfigPage, including unfinished input."""

    def __init__(self, config):
        self.config = config
        self.widgets = config.widgetsMap
        self.defaults = self.capture()

    def capture(self):
        return {key: widget.getWidgetValue() for key, widget in self.widgets.items()}

    def validate(self, values):
        if not isinstance(values, dict):
            raise ValueError("Saved settings must contain an object of form values.")
        unknown = values.keys() - self.widgets.keys()
        if unknown:
            raise ValueError(f"Unrecognized form fields: {', '.join(sorted(unknown))}.")
        for key, value in values.items():
            info = self.widgets[key].info
            kind = info["type"]
            choices = info["data"]["choices"]
            if kind == "CheckBox":
                valid = isinstance(value, bool)
            elif kind == "Listbox":
                valid = (isinstance(value, list)
                         and all(isinstance(item, str) and item in choices for item in value)
                         and len(value) == len(set(value)))
            elif kind == "Dropdown":
                valid = value is None or (isinstance(value, str) and value in choices)
            else:
                # Numeric inputs and date/file choosers are text controls. Keep
                # their text intact so even an unfinished form can be saved.
                valid = isinstance(value, str)
            if not valid:
                raise ValueError(f"Invalid saved value for {info['data']['display_name']}.")

    def apply(self, values):
        self.validate(values)
        for key, value in values.items():
            widget = self.widgets[key]
            if widget.info["type"] == "Listbox":
                for index in widget.widget.GetSelections():
                    widget.widget.Deselect(index)
            if widget.info["type"] == "Dropdown" and value is None:
                widget.widget.SetSelection(0)
            else:
                widget.setValue(value)
        self.config.resetErrors()

    def save(self, path):
        path = Path(path)
        values = self.capture()
        self.validate(values)
        payload = {"format": PRESET_FORMAT, "version": PRESET_VERSION, "values": values}
        # Replace only after serialization succeeds so an existing preset isn't
        # left truncated by a failed write.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False,
            ) as stream:
                temporary = Path(stream.name)
                json.dump(payload, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def load(self, path):
        with Path(path).open(encoding="utf-8-sig") as stream:
            payload = json.load(stream)
        if not isinstance(payload, dict) or payload.get("format") != PRESET_FORMAT:
            raise ValueError(
                "Choose a file created with File > Save Settings in the setup GUI. "
                "A project's settings.json is an analysis configuration."
            )
        if type(payload.get("version")) is not int or payload["version"] != PRESET_VERSION:
            raise ValueError("This saved settings version is not supported.")
        values = payload.get("values")
        self.validate(values)
        # Fields added after a preset was saved receive the fresh form defaults,
        # rather than inheriting the previous site's selections.
        self.apply({**self.defaults, **values})


def attach_settings_menu(frame):
    """Add file actions and visible settings buttons to the Gooey window."""
    import wx

    settings = FormSettings(frame.navbar.getActiveConfig())
    menu = wx.Menu()
    open_item = menu.Append(wx.ID_OPEN, "&Open Settings...\tCtrl+O")
    save_item = menu.Append(wx.ID_SAVE, "&Save Settings...\tCtrl+S")
    frame.GetMenuBar().Insert(0, menu, "&File")
    frame.CreateStatusBar()

    # Keep these actions visible while users move between form tabs. The native
    # toolbar sits above Gooey's client layout, so it needs no parser fields or
    # changes to Gooey's tab/console switching.
    toolbar = frame.CreateToolBar(style=wx.TB_HORIZONTAL | wx.TB_TEXT | wx.TB_NOICONS)
    toolbar.AddTool(wx.ID_OPEN, "Load Settings...", wx.NullBitmap,
                    shortHelp="Restore form choices from a saved GUI settings file")
    toolbar.AddTool(wx.ID_SAVE, "Save Settings...", wx.NullBitmap,
                    shortHelp="Save current form choices, including unfinished settings")
    toolbar.Realize()
    frame.Layout()

    def choose_file(saving):
        if frame.clientRunner.running():
            return
        title = "Save GUI Settings" if saving else "Open GUI Settings"
        style = (wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT if saving
                 else wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        with wx.FileDialog(
            frame, title, defaultFile="gui-settings.json" if saving else "",
            wildcard="GUI settings (*.json)|*.json", style=style,
        ) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            path = Path(dialog.GetPath())
        if saving and not path.suffix:
            path = path.with_suffix(".json")
            # The native overwrite prompt checked the name from the dialog;
            # check again if adding the extension changed that name.
            if path.exists() and wx.MessageBox(
                f"Replace the existing file {path.name}?", title,
                wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION, parent=frame,
            ) != wx.YES:
                return
        try:
            if saving:
                settings.save(path)
            else:
                settings.load(path)
                frame.showSettings()
                frame.Layout()
        except (OSError, ValueError) as exc:
            wx.MessageBox(str(exc), title, wx.OK | wx.ICON_ERROR, parent=frame)
            return
        verb = "Saved" if saving else "Opened"
        frame.SetStatusText(f"{verb} settings: {path}")

    frame.Bind(wx.EVT_MENU, lambda event: choose_file(False), open_item)
    frame.Bind(wx.EVT_MENU, lambda event: choose_file(True), save_item)
    # wx toolbar tools use the same command events and IDs as menu items.
    for item in (open_item, save_item):
        frame.Bind(wx.EVT_UPDATE_UI,
                   lambda event: event.Enable(not frame.clientRunner.running()), item)
    return settings


def run_settings_gui(build_spec):
    # Construct explicitly instead of patching Gooey's global parser or runner.
    # This keeps the ordinary headless worker path independent of wx windows.
    from gooey.gui.application import build_app

    app, frame = build_app(build_spec)
    attach_settings_menu(frame)
    app.MainLoop()
