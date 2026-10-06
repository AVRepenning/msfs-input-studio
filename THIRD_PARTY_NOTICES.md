# Third-party data and software

The bundled action catalogue and observed input-name/ID pairs are derived from
[highinthefssky/msfs-2024-controls-settings](https://github.com/highinthefssky/msfs-2024-controls-settings),
commit `2027bf048bbc64fc26300fb959eaa7cfb67b335f`, licensed under GPL-3.0.
The original licence is included as `LICENSE`. The app is distributed under
GPL-3.0-or-later. `data/catalogue.json` lists source filenames and SHA-256 hashes;
`tools/analyze_profiles.py` reproduces the extraction. Original bindings and
original users' device GUIDs are not included in the bundled catalogue.

English action names and browsing categories are joined by exact event ID from
[iadarroch/FSProfiles](https://github.com/iadarroch/FSProfiles), commit
`fec8c2efa289b2bb7e676306f4d383b838a32ac4`, under the MIT licence (copyright
2024 Ian Darroch). The source is `data/reference/KnownBindings2024.xml` and the
licence is `data/FSProfiles-MIT-LICENSE.txt`. `tools/enrich_catalogue.py` reproduces
the join; provenance and source digest appear in `data/catalogue.json`.
This reference supplies names for 1,652 existing action/context entries; it does
not establish exhaustive coverage or introduce guessed input IDs.

Python, Tcl/Tk and PyInstaller use their respective upstream licences.
PyInstaller's exception permits distribution of its bundled executables.
No private Store profiles, Microsoft SDK binaries or device images are
redistributed. Microsoft Flight Simulator is a Microsoft trademark. This is an
independent tool and is not affiliated with Microsoft or Asobo.
