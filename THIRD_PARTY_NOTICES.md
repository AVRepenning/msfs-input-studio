# Third-party data and software

The bundled action catalogue and observed input-name/ID pairs are derived from
[highinthefssky/msfs-2024-controls-settings](https://github.com/highinthefssky/msfs-2024-controls-settings),
commit `2027bf048bbc64fc26300fb959eaa7cfb67b335f`, licensed under GPL-3.0.
The original licence is included as `LICENSE`. The app is distributed under
GPL-3.0-or-later. `data/catalogue.json` lists source filenames and SHA-256 hashes;
`tools/analyze_profiles.py` reproduces the extraction. Original bindings and
original users' device GUIDs are not included in the bundled catalogue.

Python, Tcl/Tk and PyInstaller use their respective upstream licences.
PyInstaller's exception permits distribution of its bundled executables.
No Microsoft game files, SDK binaries, localized UI strings or device images are
redistributed. Microsoft Flight Simulator is a Microsoft trademark. This is an
independent tool and is not affiliated with Microsoft or Asobo.
