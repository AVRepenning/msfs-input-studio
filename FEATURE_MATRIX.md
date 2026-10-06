# Feature baseline and acceptance checklist

The target is the configuration features in MSFS 2024's normal Controls settings
and Input Profile / Input Device developer editors, plus easier offline setup.
This is an implementation checklist, not a claim of complete parity today.

| Feature | Current build | Remaining acceptance work |
| --- | --- | --- |
| Discover controllers and inputs | Native DirectInput | XRAY and other hardware tests |
| Read native exported profiles | 48-file round-trip checked | MSFS import test |
| Create profiles offline | General, airplane, helicopter | Generated-file validation in MSFS |
| Search, context filter, sort, bound-only | Implemented | Current simulator action coverage |
| Search by physical input | Implemented | Physical capture test |
| Primary, secondary, chords | Implemented | Simulator interpretation |
| Individual and guided recording | Implemented; simulated stream tested | Physical guided-session test |
| Split axes and directional hats | Verified input IDs supported | Missing base/split/extra hat references |
| Analog, digital, axis, invert | Flag editor | In-flight checks |
| Held, initial press, release, hold delay | Flags and delay editor | In-flight behavior checks |
| Ctrl, Shift, Alt and SDK modifiers | All 16 documented flag bits | Keyboard modifier capture / cross-device chords |
| Custom event value | Field and flag editor | Profile-type restrictions |
| Global axis parameters | All six documented fields | Runtime curves/ranges |
| Per-binding axis overrides | Both binding slots | SDK/runtime restriction checks |
| Live raw input display | Implemented | Physical motion, disconnect/reconnect |
| Name every button and axis | Implemented, including unknown IDs | XRAY labels after reconnect |
| Share controller labels | Local library and `.studio.json` | Another-computer test |
| Possible conflicts | Same chord in same context | Cross-context / subset guidance |
| Duplicate, undo, redo | Implemented | Full named history and batch editor |
| Unknown XML and metadata | Preserved semantically | More export versions |
| Aircraft-specific profiles | Existing metadata retained | Creation UI and real aircraft references |
| All actions and display categories | 3,719 observed entries | Complete current action database / labels |
| Other aircraft categories | Imported XML retained | Creation UI and category references |
| Keyboard/mouse, native XInput | Not implemented | Real ID/name and device-format references |
| Device/composite metadata editor | Detected or imported identity | Full editor and composite detection |
| DeviceConfig labels / merge icons | Not implemented | Editor, assets and MSFS test |
| Developer Device Keys tables | Learned IDs, unknowns blocked | Complete official reference tables |
| ActionDB / remapDB | Not implemented | Database references and editors |
| SDK package / Community install | Not implemented | Built sample, paths, validation |
| Portable offline executable | One-file build; packaged smoke passed | User hardware/import test |

Recording captures inputs/chords and guides a sequence of action assignments;
it does not inject or replay timed gameplay macros. Labels are aliases in this
app. MSFS input identifiers remain unchanged. MSFS does not read the sidecar.
Native Controls-menu import is the current delivery route; it does not establish
SDK device-package compatibility. Third-party aircraft were initially deferred;
their developer features remain on the full-parity checklist.

References:

- [Controller import/export](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles)
- [Input Profile Editor](https://docs.flightsimulator.com/msfs2024/retail/devmode/editors/input-editors/the-input-profile-editor/)
- [Input Device Editor](https://docs.flightsimulator.com/msfs2024/html/2_DevMode/Input_Editors/The_Input_Device_Editor.htm)
- [Input XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Input_Configuration_XML_Properties.htm)
- [DeviceConfig XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/DeviceConfig_XML_Properties.htm)
- [ActionDB XML](https://docs.flightsimulator.com/msfs2024/html/5_Content_Configuration/Input/Actiondb_XML_Properties.htm)
- [InputProfiles SDK sample](https://docs.flightsimulator.com/msfs2024/retail/samples-tutorials/samples/misc/inputprofiles/)
