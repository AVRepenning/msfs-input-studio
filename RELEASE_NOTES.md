Portable Windows controller-profile editor for use with MSFS 2024 closed.

v0.2.2 fixes:

- Camera/view controls no longer leave an unexplained empty list when browsing an Airplane or Helicopter profile. The list explains that matching controls belong to General profiles and offers Show matching controls from all profiles, preserving the search and existing bindings.
- Unified the Camera and Camera / views browsing groups, bringing all 470 known camera/view entries together. Native profile categories and control IDs are preserved.
- Added clear guidance and a Clear filters button for other empty results, including conflicting bound/unbound filters.

v0.2.1 fixes:

- Fixed the Saved-browser freeze caused by repeatedly rebuilding each profile's action map while counting bindings. Counting 30 local profiles dropped from about 40 seconds to 0.17 seconds with identical results.
- Saved now opens immediately, scans in the background, shows loading progress and provides Refresh/retry feedback. Existing results remain usable after a scan failure. Closing the app cancels the scan.
- Flaps and other aircraft controls now explain why a General profile cannot bind them and offer a matching profile. Empty profiles can switch type while keeping their name, device identity and axis tuning; Undo/Redo restores the change. Profiles with existing controls use a separate New profile dialog.
- The profile-type dropdown is available, disabled recording buttons have a clear disabled appearance, and conflict detection avoids repeated action-map rebuilding when opening large profiles.

- Prominent recording, countdown, detected-input, retry, stopped and saved feedback; an always-accessible Stop listening button.
- Windows-style numbered button lights, XY position and every reported axis with numeric values and scales. A larger controller-test window supports naming inputs.
- Independent airplane/helicopter/general browsing, English names for 1,652 catalogue entries, groups, bound/unbound filters and guided setup.
- Press an input to select and scroll to its assignments. Follow mode supports repeated searches; modifier flags and split-axis bindings are included.
- Slower chord capture, dominant-axis detection, guided progress and release handling for permanently held switches.
- Keyboard/mouse capture and an XInput backend, enabled by real profile references. Store profiles are opened as copies and extend the local reference library.
- Local automatic working copies, compressed named undo history, batch editing and device/aircraft metadata editing.
- Device Keys reference browser, DeviceConfig/ActionDB/remapDB source editors and SDK DefaultInput export. Imported numbered axes remain editable.

Validation: 45 automated tests, semantic round trips across 48 public profile exports, 20 controller/UI workflow checks, 7 keyboard/mouse workflow checks, 14 Saved/flaps regression checks and 8 camera workflow checks. The Saved browser was tested against 30 real local profiles, including opening the largest as a copy. Camera checks reproduce the hidden list and record a simulated button binding in a separate General profile while preserving existing flaps bindings. Input streams are simulated; the connected PowerA FlightDeck reports 7 axes and 27 buttons. Native readers and the packaged executable are checked on Windows.

This is a test build. XRAY hardware, generated-profile import and in-flight behavior still need simulator validation. Exhaustive current action coverage, VR/proprietary devices, SDK image/layout authoring and package deployment remain incomplete; see FEATURE_MATRIX.md.

Download **MSFSInputStudio.exe** to run without installing Python. **MSFSInputStudio-source.zip** contains the corresponding source, licences and public reference fixtures. Your private Store profiles and local working copies are not included.
