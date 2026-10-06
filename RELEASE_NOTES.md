v0.3.0 makes General and aircraft profiles parts of one controller setup.

- Switch General/Airplane/Helicopter without replacing profiles or opening a New dialog. Bindings, names, tuning, browsing state and each layer's Undo/Redo history remain intact.
- Selecting a camera control opens General automatically; selecting flaps opens Airplane. All controls and Bound only show existing bindings from the relevant layers together, with a Stored in column.
- Find input and Follow controller navigate to bindings across layers. Guided recording can cover General and aircraft actions in one sequence.
- Save setup stores all profiles and input names in one portable `.msfssetup` file. Open controller setup restores them. Complete setups autosave locally and recover at startup. Reopening an older saved setup retains newer edits as another working copy.
- Export setup creates separate native XML profiles, input-name sidecars and an import guide. Existing files are kept. Import each file for the same controller under its matching type, then select one General and one aircraft preset together in MSFS.
- Imported and duplicated presets stay selectable alternatives. Existing aircraft-specific metadata is preserved. Use for setup copies every layer to another controller of the same input format and keeps the original.
- Clear New setup / Save setup / MSFS presets / Export setup buttons, matching feedback and walkthrough. All four remain accessible at the minimum window size. MSFS presets still load asynchronously with progress/retry feedback.

The profile workflow follows [Microsoft's Controls FAQ](https://flightsimulator.zendesk.com/hc/en-us/articles/16459737949980-Controller-Settings-FAQ), [SDK profile/context rules](https://docs.flightsimulator.com/msfs2024/retail/content-configuration/input/input-profiles/) and [import instructions](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles). General and aircraft files remain separate on export because MSFS can ignore actions stored in a disallowed profile context. MSFS_DOCUMENTATION_REVIEW.md records the audit and remaining gaps.

Validation: 56 automated tests, semantic round trips across 48 public profile exports, and 65 actual Tk UI checks (20 controller, 7 keyboard/mouse, 14 MSFS-presets/flaps, 8 camera, 16 complete-setup workflow). Recording streams are simulated. Windows enumerates the PowerA FlightDeck's 7 axes and 27 buttons. The MSFS-presets browser was also checked against 30 local Store profiles, read only.

The v0.3.0 portable executable launched successfully outside the source directory. Its embedded catalogue loaded all 3,719 entries, Windows opened the controller, and General/Airplane switching retained the original profile. The packaged startup check exited normally.

This is a test build. XRAY hardware, generated-profile import and in-flight behavior still need validation. Exhaustive current action coverage, creating additional aircraft categories/model identifiers, complete cross-layer runtime conflict analysis, VR/proprietary devices and SDK package deployment remain incomplete. See FEATURE_MATRIX.md. Saved setups preserve XML and names; session Undo history is not stored in the setup file.

Download **MSFSInputStudio.exe** for the portable build. **MSFSInputStudio-source.zip** contains the corresponding source, licences and public reference fixtures. Private Store profiles, controller names and local working copies are not included.
