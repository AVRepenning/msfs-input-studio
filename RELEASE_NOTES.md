Portable Windows controller-profile editor for use with MSFS 2024 closed.

- Prominent recording, countdown, detected-input, retry, stopped and saved feedback; an always-accessible Stop listening button.
- Windows-style numbered button lights, XY position and every reported axis with numeric values and scales. A larger controller-test window supports naming inputs.
- Independent airplane/helicopter/general browsing, English names for 1,652 catalogue entries, groups, bound/unbound filters and guided setup.
- Press an input to select and scroll to its assignments. Follow mode supports repeated searches; modifier flags and split-axis bindings are included.
- Slower chord capture, dominant-axis detection, guided progress and release handling for permanently held switches.
- Keyboard/mouse capture and an XInput backend, enabled by real profile references. Store profiles are opened as copies and extend the local reference library.
- Local automatic working copies, compressed named undo history, batch editing and device/aircraft metadata editing.
- Device Keys reference browser, DeviceConfig/ActionDB/remapDB source editors and SDK DefaultInput export. Imported numbered axes remain editable.

Validation: 38 automated tests, semantic round trips across 48 public profile exports, 20 controller/UI workflow checks and 7 keyboard/mouse workflow checks. Input streams are simulated; the connected PowerA FlightDeck reports 7 axes and 27 buttons. Native readers and the packaged executable are checked on Windows.

This is a test build. XRAY hardware, generated-profile import and in-flight behavior still need simulator validation. Exhaustive current action coverage, VR/proprietary devices, SDK image/layout authoring and package deployment remain incomplete; see FEATURE_MATRIX.md.

Download **MSFSInputStudio.exe** to run without installing Python. **MSFSInputStudio-source.zip** contains the corresponding source, licences and public reference fixtures. Your private Store profiles and local working copies are not included.
