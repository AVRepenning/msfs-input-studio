# MSFS Input Studio

A portable, English-language Windows editor for MSFS 2024 controller profiles.
Create and edit profiles with the simulator closed, then import the exported XML
through MSFS Controls. No Python, SDK, account or network connection is needed
to run the executable.

[Download v0.3.0](https://github.com/AVRepenning/msfs-input-studio/releases/tag/v0.3.0).
This repository and its downloads are private. The updated local executable is
`dist/v0.3.0/MSFSInputStudio.exe`; an earlier open executable can remain running.

**Status: test build, with simulator and XRAY validation still outstanding.**
Complete feature parity has not been established; see `FEATURE_MATRIX.md`.

## Set up a controller

1. Connect the controller, start the app and select it. **Refresh** discovers
   hardware connected after startup. **Test controller** opens numbered button
   lights, XY position, numeric axis values and scales. Click an input, enter a
   useful name, then **Set name**.
2. Click **New setup**. Switch **Editing** between General, Airplane and
   Helicopter to configure one controller setup. Each layer keeps its bindings,
   name, tuning, browsing state and Undo/Redo history when you switch.
   Selecting a camera action opens General automatically; selecting flaps opens
   Airplane. Both remain in the setup. **MSFS presets** loads local Store saves
   in the background with progress/retry feedback. **Open XML** adds a simulator
   export as another preset for the same controller, preserving earlier edits.
   Imported aircraft-specific metadata remains in a separate selectable preset.
3. **Show** changes which controls you browse without changing the profile.
   **All controls** is the default and shows bindings from the relevant setup
   layers together. **Stored in** identifies the layer each action edits.
   Search names, event IDs, contexts and assigned input labels; filter by group,
   context, bound/unbound or possible conflicts. Column headings sort the list.
   Camera/view controls use General. If a restricted view hides all
   matching controls, the list explains why and offers **Show matching controls
   from all profiles** while preserving your search. **Clear filters** handles
   other empty searches. Camera source groups appear together as **Camera / views**.
4. Select an action and click **Get Input** in Primary or Secondary. The panel
   shows recording state, remaining time, detected inputs and the result. Press
   chords together or move the intended axis. Diagonal stick movement captures
   the dominant axis. **Listen to** restricts capture to buttons/keys, axes or
   hats. Split-axis/split-hat options support directional inputs. **Use** and
   **Add to chord** offer manual assignment from the input list.
5. **Guided setup** offers starter controls for the current type. Select actions
   with Ctrl/Shift and **Record selected** for your own sequence, including
   General and aircraft actions in one session. The app switches layers as needed
   and waits
   for recorded buttons to release and axes to settle. **Skip**, **Stop**,
   **Try again** and **Continue anyway** handle interruptions.
6. **Find input** listens and jumps to its assigned action across the setup,
   switching to the profile holding the binding. **Follow controller**
   does this repeatedly. Search clears hiding filters and includes keyboard
   modifiers stored in flags. Review **Behavior**, **Axis tuning** and conflicts.
7. **Edit selected…** or right-click offers batch clearing/behavior. **Undo**,
   **Redo** and Tools → **Undo history** restore named states. Snapshots are
   compressed to keep memory use down.
8. **Save setup** (Ctrl+S) stores all profiles and input names together in one
   `.msfssetup` file. Tools → **Open controller setup** (Ctrl+O) reopens it in this app.
   **Export setup** creates a separate native XML for every profile, alias
   sidecars and `IMPORT-SETUP.txt`. Existing files are kept; repeated exports
   receive numbered filenames. In MSFS Settings → Controls, select the same
   device and matching profile type, open its cogwheel and import each XML.
   Select one General preset and one aircraft preset together. Presets of the
   same type are alternatives. Set aircraft/default assignment in MSFS and test
   in flight. Tools → **Export current profile XML** exports just the profile being edited.

See [Microsoft's import/export instructions](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles).

Capture times out after 12 seconds and settles 0.65 seconds after the last new
input. Escape stops recording unless **Allow recording Escape** is selected;
the panel's **Stop listening** remains available. Failed capture preserves the
old binding and pauses a guided session for retry/skip. Recording assigns
controls; it does not replay timed gameplay macros.

## Working copies, profiles and names

The entire setup is saved to a local working copy every three seconds and before
switching layers or opening another setup. Startup restores the most recent
setup matching the controller. Tools → **Resume local working copy** opens other
setups and older single-profile drafts. Reopening an older saved setup keeps the
newer edits as another working copy. Undo history is retained while switching
in the current session; saved setup files preserve XML and names, not Undo history.
Save setup and exported XML remain separate from simulator saves. Saving into
the managed Store cloud-save folder is blocked.

**MSFS presets** reads profile XML copies from the Microsoft Store WGS folder, without
modifying them. Copies supply real input IDs, device identity and extra actions.
When references exist, keyboard/mouse profiles enable native Windows capture;
XInput references enable connected XInput gamepads. Open XML can supply exported
references for these formats too.

Names are aliases tied to the controller, without replacing MSFS's internal
names/IDs. They persist locally and travel with exports in an adjacent
`.studio.json` sidecar. Keep it alongside XML when sharing with this app; MSFS
reads only XML. App data lives in `%LOCALAPPDATA%/MSFSInputStudio`:
`controller_labels.json`, `learned_catalogue.json`, `setups/`, `drafts/` and `error.log`.

Changing the live controller keeps the setup's identity. **Use for setup** copies
all layers to a controller of the same input family and retains the original;
review every assignment. Create a new setup to switch between keyboard,
mouse, gamepad and joystick, which use different input-ID formats.

## Settings and developer tools

- Primary/secondary slots and multi-key chords.
- All 16 documented flag bits, numeric flags, custom event value and delay.
  Digital repeats while held; Once on press sends once; On release sends on
  release; Delayed / hold uses delay. Simulator behavior still needs validation.
- All six axis fields: positive/negative sensitivity, inner/outer deadzones,
  neutral and response rate, globally or in either slot. Imported GameInput
  numbered axes retain their identity and are editable, without assuming a
  DirectInput mapping. Values show raw normalized controller input, not an
  emulation of MSFS's response curve. Mouse movement is a relative pixel preview.
- Profile/device metadata, including existing aircraft-specific fields.
- Device Keys reference browser and reference-profile/ActionDB imports.
- Structured DeviceConfig, ActionDB and remapDB source editors: device labels,
  MergeIcons, action type/category/description, meta-contexts and remap AND/OR
  alternatives. Unknown XML fields and comments remain intact.
- SDK DefaultInput export, keeping its distinction from native import files.

SDK tools edit source XML. Texture/device-layout authoring, package building and
Community deployment are incomplete. The SDK is not installed here; source
validation does not establish SDK or simulator acceptance.

## Reference coverage and limitations

The bundled library has **3,719 action/context entries** and **72 exact joystick
input-name/ID pairs** from 48 public MSFS 2024 exports. English names and groups
cover **1,652 entries**, joined by exact event ID from MIT-licensed FSProfiles.
Other labels derive from event names. This is not a complete current SDK database.

Local scans/imports learn real references. IDs are scoped to joystick, keyboard,
mouse and gamepad; keyboard punctuation remains distinct. Contradictory IDs are
quarantined for new assignments, while imported bindings retain their numbers.
**Needs reference** inputs never receive extrapolated IDs. Import a real profile
containing the input to learn its mapping.

DirectInput polls the standard layout of up to eight axes, four hats and 128
buttons. XInput, keyboard and mouse use separate readers. VR/proprietary devices,
GameInput beyond that DirectInput layout and device-specific extensions remain
incomplete. XRAY's enumeration has not been tested. Composite controllers may
need an actual export to establish CompositeID/hardware metadata. New detected
DirectInput profiles default to CompositeID 0 and hardware version 1.0.0.0.

Native profiles have multiple top-level elements. The parser's internal wrapper
is removed on export. Unknown XML, comments, chords, secondary slots, aircraft
metadata and overrides are preserved semantically; whitespace can change.
SDK DefaultInput files retain their format and are not asserted to be native
Controls-menu imports. General and aircraft layers remain separate native XML
files because disallowed action contexts can be ignored by the simulator.
Read [the documentation review](MSFS_DOCUMENTATION_REVIEW.md) for the rules used
in this pass and the remaining gaps. Conflict checks remain within each profile
and context; they do not establish runtime precedence across every active layer.

## Build and verify

Use 64-bit Windows Python 3.12+ with Tkinter. `build.bat` installs pinned tools,
runs tests, builds a windowed one-file executable into `dist/v0.3.0` and creates
a source archive there. Intermediate files go to LocalAppData to avoid OneDrive
locks. The source archive includes the public fixtures; a fresh Git checkout
needs these retrieved separately:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
git clone --depth 1 https://github.com/highinthefssky/msfs-2024-controls-settings.git research/community-profiles
build.bat
```

Fixture revisions/licences are in `THIRD_PARTY_NOTICES.md`. Regenerate with
`python tools/analyze_profiles.py`, then `python tools/enrich_catalogue.py`.
Private Store profiles and working copies are not packaged.

Validation:

- 56 automated tests, including semantic round trips across all 48 public
  fixtures, per-family identity/conflicts, numbered axes, SDK data, XInput
  translation, read-only scans and working-copy preservation.
- 20 actual Tk controller/UI workflow checks and seven keyboard/mouse checks,
  with simulated press/motion streams. Slow chords, held switches, retry, Escape,
  navigation, labels, batch undo, working-copy recovery and export are exercised.
- 14 MSFS-presets/flaps workflow checks cover background loading, failure/retry,
  close/reopen/cancellation, cached counts, large-profile opening, profile-type
  layer switching and preservation. A simulated flaps-axis recording is
  verified against the connected controller's real Windows inputs.
- Eight camera workflow checks reproduce hidden controls, reveal all 470 known
  camera/view entries, preserve filters and airplane bindings, and record a
  simulated camera button binding in a separate General profile.
- 16 controller-setup workflow checks exercise General/Airplane/Helicopter
  switching, independent histories/tuning, combined binding display, input
  search/Follow across layers, portable save/reopen, preservation of newer edits,
  complete export, alternate presets, startup recovery and mixed-layer guided
  recording. Save/export buttons are checked at the minimum 1120×680 window size.
- Windows enumerates the connected PowerA FlightDeck's seven axes and 27 buttons.
  Keyboard/mouse readers initialize. Physical manipulation and a connected
  native XInput device have not been tested.
- Screenshots inspected at regular/smaller sizes. The full test window displays
  all seven axis scales and 27 button lights; smaller panels scroll.
- Source startup and resource loading are checked outside the source directory.
  See release notes for the current executable's launch verification.

`tools/qa_ui.py` and `tools/qa_workflow.py` use Pillow for development screenshots.
`tools/qa_system_workflow.py` needs local keyboard/mouse reference profiles.
`tools/qa_saved_workflow.py` reproduces Saved and flaps setup, using Pillow
and the connected controller; it also reads local Store profiles when present.
`tools/qa_camera_workflow.py` checks camera discovery, filter guidance and capture.
`tools/qa_setup_workflow.py` exercises the complete controller setup workflow.
Pillow is not needed to build or run the app.

```powershell
dist/v0.2.3/MSFSInputStudio.exe --smoke-test app-smoke.json
dist/v0.2.3/MSFSInputStudio.exe --diagnose controller-diagnostics.json
```

Next acceptance: connect XRAY, check its live inputs, export one verified axis
and button, import into the matching MSFS preset type, and test in flight.
Then test secondary, held/release, curves and General controls. If import fails,
compare a real working export from the same controller/type.

## Sources and licence

- [Input Profile Editor](https://docs.flightsimulator.com/msfs2024/retail/devmode/editors/input-editors/the-input-profile-editor/)
- [Input configuration XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Input_Configuration_XML_Properties.htm)
- [DeviceConfig XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/DeviceConfig_XML_Properties.htm)
- [ActionDB XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Actiondb_XML_Properties.htm)
- [Public reference profiles](https://github.com/highinthefssky/msfs-2024-controls-settings)
- [English action metadata](https://github.com/iadarroch/FSProfiles)

GPL-3.0-or-later; see `THIRD_PARTY_NOTICES.md`. Independent of Microsoft/Asobo.
