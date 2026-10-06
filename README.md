# MSFS Input Studio

A small, English-language, offline Windows editor for Microsoft Flight Simulator
2024 controller profiles. It detects controllers through Windows DirectInput,
reads buttons, axes and hats, and exports XML for the simulator's Controls-menu
import. MSFS does not need to run while you create or edit profiles.

**Status: first runnable build, awaiting simulator validation.** XML preservation,
Windows enumeration/polling and app commands have been tested. Importing a newly
generated profile and flying with it have **not** been tested in MSFS 2024 yet.
This is not a claim of complete support for every device or every simulator action.

The expanded settings/developer-menu baseline is tracked in `FEATURE_MATRIX.md`.
The current build is ready for initial hardware/import testing; full feature
parity remains work in progress.

## Run

Double-click `dist/MSFSInputStudio.exe`. No Python installation, SDK, account,
administrator privileges or internet connection are required to run it. Connect
the controller before starting, or click **Refresh** after connecting it.

For source development, use Python 3.12 or newer with Tkinter:

```powershell
python msfs_input_studio.py
```

## Set up controls

1. Select a Windows controller. Its axes, buttons and hats are read from Windows;
   there is no model-specific MeridianGMT XRAY definition.
2. Select **General controls**, **Airplane controls** or **Helicopter controls**.
   Each type is a separate profile. Changing type creates a new profile, with an
   unsaved-changes prompt if necessary.
3. Search by action name, event ID or context. Click column headings to sort;
   filter by context or show only bound actions. **All profile types** shows
   actions from other types, but prevents assigning them to an incompatible type.
4. Select a control, then **Get Input** and press/move the controller. You can
   also choose a reported input and click **Use**. **Add to chord** combines it
   with the existing input. Use **Secondary** for an alternative binding.
5. In **Behavior**, choose the required flags and click **Apply behavior**.
   Digital normally repeats while held; **Once on press** sends one event;
   **On release** sends on release. **Delayed / hold** uses **Delay (s)**.
   Full-range axes automatically get the Axis type when bound. Numeric flags
   remain editable for advanced use and imported values are preserved.
6. **Axis tuning** supports positive/negative sensitivity, inner/outer deadzones,
   neutral and response rate, globally or per primary/secondary binding. Click
   **Apply axis settings**. The live indicator displays raw Windows position;
   it does not pretend to reproduce MSFS's undocumented response-curve math.
7. **Export XML**, then import it in MSFS when you want to use it.

**Live inputs** shows the controller's raw values and whether an MSFS input ID
is available. Capture times out after 12 seconds; Escape cancels. Undo/redo
stores up to 60 edit states. Duplicate gives a profile a new name; exports always
use a Save As dialog, so you choose where the XML is written.

### Guided recording, input search and controller names

Use Ctrl/Shift to select several actions and click **Record selected**. Choose
Primary or Secondary before starting. The app records one action at a time,
waits for buttons/hats to release and axes to settle, then advances. **Skip**
leaves an action unchanged; **Stop** keeps the bindings already recorded. Unknown
MSFS input IDs are still blocked. This records assignments, not timed macros.

**Find input** listens for a physical input and filters to actions using it.
**Clear input filter** removes that filter. **Conflicts** shows potential reuse
of the same complete chord by different actions within the same context. Reuse
can be intentional; the app does not erase other bindings automatically.

In **Live inputs**, select a row, enter a name such as Landing gear or Roll, then
click **Set name**. You can name every reported button/axis, including inputs
whose MSFS ID is not yet known. **Reset** restores the Windows name. Labels
appear in the picker and binding list, persist in
`%LOCALAPPDATA%/MSFSInputStudio/controller_labels.json`, and are included in an
adjacent `.studio.json` file when exporting a named controller profile. Keep
that sidecar with the XML when sharing profiles with this app. MSFS imports only
the XML; labels do not replace its internal input names or numeric IDs.

## Add the profile to MSFS 2024

Microsoft now documents native controller profile import. The older handoff's
Community-package route is not required for this workflow:

1. Open MSFS 2024 → **Settings → Controls**.
2. Select the **same controller** used when creating the exported file.
3. Click the cogwheel for the matching **General / Airplane / Helicopter** profile.
4. Choose **Import**, select the XML, and select the resulting preset.
5. Set your desired aircraft/default assignment, then test in flight.

General and aircraft controls must be imported into their respective profile
types. For standard aircraft you can create an Airplane preset here and assign
it to the aircraft in MSFS. Existing aircraft-specific metadata is preserved when
opening a real exported profile. Creating third-party aircraft action databases
or inventing aircraft identifiers is not supported.

See [Microsoft's import/export instructions](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles).

## Real input IDs, with no guessed bindings

`data/catalogue.json` contains **3,719 action/context entries** and **72 exact
input-name/ID pairs** observed in 48 public, real MSFS 2024 exports. The action
list includes controls not currently bound in those files. Names are readable
event IDs, not the simulator's localized labels. Coverage is broad, but is
limited to those exports and can differ from your simulator version.

The SDK does not document the numeric input-ID encoding. No unobserved button
ID or axis name is extrapolated. For example, Button 1's ID 0 is verified; some
higher-numbered buttons have no reference yet, even though Windows detects them.
Those inputs are marked **needs reference** and cannot be bound/exported with an
invented ID. **Open XML** containing that input learns the real mapping and any
new actions. Learned mappings persist in
`%LOCALAPPDATA%/MSFSInputStudio/learned_catalogue.json`. Conflicting IDs are
quarantined for new bindings rather than silently replaced. Already imported
bindings keep their original numbers during round-trip editing.

The Windows instance GUID and product ID are detected through DirectInput. New
profiles use `CompositeID=0` and `HWVer=1.0.0.0`; these values are not verified for
every composite device. If XRAY exposes multiple logical controllers, or MSFS
rejects its identity, open one real export from that logical controller so its
metadata is preserved. A one-time reference export may therefore be necessary
for inputs or devices outside the verified library. Subsequent editing works
with MSFS closed. Initial creation for arbitrary unsupported hardware without
ever opening MSFS is **not yet guaranteed**.

DirectInput game controllers are supported in this build. XInput-only controls,
VR devices, proprietary panels, keyboard/mouse capture, and controller-specific
features beyond the standard 8 axes, 4 hats and 128 buttons are not validated.
Changing the live controller does not automatically retarget an open profile;
**Use for this profile** explicitly transfers its Windows identity. Review all
bindings when transferring between physical controllers.

## XML formats and package findings

Real Controls-menu exports are **XML fragments** with multiple top-level nodes:
`Version`, `FriendlyName`, and `Device`; they are not a single-root XML document.
The parser uses an internal wrapper and removes it during serialization. It
preserves unknown elements/attributes, comments, multiple keys per binding,
secondary bindings, `AircraftInfo`, per-binding curves, flags, delay, and values.
Whitespace and formatting can change; the test compares semantic data.

SDK files use a `DefaultInput` root. They can be opened and edited without
converting their format. A saved SDK file is **not claimed to be a native
Controls-menu import file**. Use a native export or New for that workflow.

The app detects Store and Steam package locations from `UserCfg.opt`. On this
computer it found the Microsoft Store configuration and both `Community2024`
and `Community`. It does not edit Xbox WGS/cloud-save files or Microsoft game
packages. Automatic Community installation, `manifest.json`/`layout.json`,
`DeviceConfig.xml`, texture generation and SDK package building are **not enabled**.
Their exact loading behavior has not been validated. Writing a plausible folder
structure would not demonstrate that MSFS loads the resulting preset.

SDK documentation says positive sensitivity is 0–100 and negative sensitivity
is −100–0. Real exports include other values on both sides, so this editor uses
−100–100 for both. This is an observed compatibility decision, not a claim that
the SDK text was tested against every simulator release.

## Build a portable executable

Use 64-bit Windows Python 3.12+ with Tkinter. `build.bat` uses the project's venv
when present, otherwise `python` on PATH. It installs the pinned build tools,
runs the tests, and runs PyInstaller with `--onefile --windowed`.
Intermediate build files go to `%LOCALAPPDATA%/MSFSInputStudio/build` to avoid
OneDrive locks on the project directory; the executable is written to `dist`.

To retrieve the 48 XML fixtures needed for the corpus test:

```powershell
git clone --depth 1 https://github.com/highinthefssky/msfs-2024-controls-settings.git research/community-profiles
```

The reference revision is recorded in `THIRD_PARTY_NOTICES.md`; the corpus should
contain 48 files. If upstream changes, use that revision for reproducibility.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
build.bat
```

To regenerate the catalogue: `python tools/analyze_profiles.py`.
GUI QA (`tools/qa_ui.py`) additionally needs Pillow, available in the development
runtime used here; Pillow is not part of the app or its build requirements.

## Verification and first in-simulator test

Completed checks:

- All 48 public native export files: read → write → read preserves semantic XML.
- Tests cover unknown data, chords, secondary bindings, SDK documents, input ID
  zero, missing IDs, conflicts, axis validation and capture noise/hat direction.
- Windows DirectInput initialized and opened the connected **Xbox Series X
  PowerA FlightDeck Wireless**, reporting **7 axes and 27 buttons**. Polling
  succeeded. Physical manipulation of those controls was not performed.
- Automated UI commands tested search, binding, axis overrides, XML export and
  undo/redo, plus a simulated two-action guided recording session, controller
  naming and sidecar export; the application screenshot was inspected for layout.
- The packaged 64-bit windowed executable passed startup/capture initialization
  from a different working directory, loading its embedded catalogue and opening
  the connected controller without relying on source-file paths.

Still needs your test in MSFS:

1. Plug in MeridianGMT XRAY and run the app. Check reported counts and live values.
2. Create an Airplane profile with one verified axis and one verified button.
3. Export, then import under XRAY's Airplane profile cogwheel.
4. Check the preset appears and both bindings function in flight.
5. Test held/release behavior, curves, secondary bindings and a General profile.

If import fails, record the error and export a small working profile from MSFS
for the same controller and type. That will let us compare the actual required
metadata rather than guess. This build is ready for that validation step, not
certified as finished in-game.

For startup failures see `%LOCALAPPDATA%/MSFSInputStudio/error.log`.
Unattended diagnostic options:

```powershell
dist/MSFSInputStudio.exe --diagnose controller-diagnostics.json
dist/MSFSInputStudio.exe --smoke-test app-smoke.json
```

## Sources and licence

- [Input Profiles](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Input_Profiles.htm)
- [Input Configuration XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Input_Configuration_XML_Properties.htm)
- [DeviceConfig XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/DeviceConfig_XML_Properties.htm)
- [Device Profiles](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Device_Profiles.htm)
- [ActionDB XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Actiondb_XML_Properties.htm)
- [Input Device Editor](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Input_Editors/The_Input_Device_Editor.htm)
- [Input Profile Editor](https://docs.flightsimulator.com/msfs2024/retail/devmode/editors/input-editors/the-input-profile-editor/)
- [Developer Mode](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Developer_Mode.htm)
- [Reference exports](https://github.com/highinthefssky/msfs-2024-controls-settings)
- [Windows DirectInput device enumeration](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/ee417804(v=vs.85))

GPL-3.0-or-later. See `LICENSE` and `THIRD_PARTY_NOTICES.md`. The original prototype
was not supplied and no public download for its exact filename was found; this
implementation was rebuilt from the handoff and the verified export examples.
