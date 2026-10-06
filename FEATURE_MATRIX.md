# Feature baseline and acceptance checklist

The target is MSFS Controls settings and the SDK input editors, plus easier
offline setup. Source editing is distinguished from simulator acceptance.
This is not a claim of complete parity.

| Feature | v0.2.3 | Remaining work / acceptance |
| --- | --- | --- |
| Windows discovery/live inputs | DirectInput, keyboard/mouse, XInput reader | XRAY, physical XInput, VR/proprietary devices |
| Native profile read/export | 48 public round trips | Generated-file import and in-flight test |
| General/Airplane/Helicopter | Explicit New, mismatch guidance, safe blank type switch with Undo | Simulator aircraft/default assignment |
| Browsing | Independent filters, unified camera group, empty-list explanation/reveal/reset | Complete current action database |
| English names | 1,652 joined entries, event-name fallbacks | Remaining controls and localization tokens |
| Individual/guided capture | Countdown, detection, saved/retry/timeout, pause/skip | Physical sessions |
| Test panel and input names | Button lights, XY, numeric axis scales, scroll/popup | XRAY enumeration and reconnect |
| Press to find | Select/focus/scroll, Follow, flag modifiers | More real device formats |
| Primary/secondary/chords | Slow-chord settlement, both slots | Simulator interpretation |
| Split axes/hats | Verified references, dominant axis, input-kind filter | Missing IDs and GameInput live mapping |
| Action behavior | All 16 known bits, numeric flags, value/delay | Runtime restrictions and combinations |
| Held/press/release/hold delay | Documented flags and delay | In-flight timing |
| Ctrl/Shift/Alt | Keyboard inputs and flags | Cross-device physical combinations |
| Axis tuning | All six fields, global and both slot overrides | Actual simulator curves/ranges |
| GameInput numeric axes | Preserve/edit observed identities | Native GameInput capture |
| Working copies | Autosave, resume browser | Multi-computer sharing |
| Undo and batch | Compressed named history, clear/behavior | Long user sessions |
| Conflicts | Exact/subset chords within a context, advisory | Context/modifier precedence |
| Metadata | Existing Device/FriendlyName/AircraftInfo/SDK fields | New aircraft IDs, composite detection |
| Saved Store presets | Background read-only scans, progress/retry, cached counts, copy opening | Other distribution save layouts |
| Device Keys | Per-family browser/import, conflicting IDs blocked | Complete official reference data |
| DeviceConfig | Source editor, labels, MergeIcons and identity fields | Images/layout/textures and SDK build |
| ActionDB | Fields, types/categories, meta-contexts, library import | Full databases and simulator loading |
| RemapDB | AND/OR alternatives, source round trips | Runtime remapping/deployment |
| SDK DefaultInput | Preserve existing format and export copy | SDK and simulator acceptance |
| Unknown XML | Semantic attribute/element/comment preservation | More export versions |
| Share aliases | Local names and .studio.json sidecar | Another-computer test |
| Portable exe | Versioned one-file build and smoke check | User hardware/import test |
| SDK package/Community install | Incomplete | Sample build, manifest/layout, loading/rollback |
| Third-party aircraft/device assets | Source structures and imported metadata | Packages, localization and visual assets |

DirectInput uses the standard eight-axis/four-hat/128-button layout. Imported
profiles can preserve fields beyond live-reader support. Unknown IDs are not
invented. The absence of the SDK and XRAY prevents claiming exhaustive parity
or finished in-simulator behavior.

References:

- [Controller import/export](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles)
- [Input Profile Editor](https://docs.flightsimulator.com/msfs2024/retail/devmode/editors/input-editors/the-input-profile-editor/)
- [Input Device Editor](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Input_Editors/The_Input_Device_Editor.htm)
- [Input configuration XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Input_Configuration_XML_Properties.htm)
- [DeviceConfig XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/DeviceConfig_XML_Properties.htm)
- [ActionDB XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Actiondb_XML_Properties.htm)
- [InputProfiles SDK sample](https://docs.flightsimulator.com/msfs2024/retail/samples-tutorials/samples/misc/inputprofiles/)
