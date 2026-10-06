# MSFS 2024 documentation review — 7 October 2026

The controller setup workflow was checked against Microsoft's Controls FAQ,
SDK profile documentation and current import/export instructions. One controller
setup in this app holds the distinct simulator profiles together. Switching the
editor retains earlier work; export preserves the simulator's file structure.

## Documented rules and implemented behavior

| Documented rule | App behavior in v0.3.0 |
| --- | --- |
| General, aircraft category and specific aircraft presets have distinct scopes. General bindings apply across aircraft. | General/Airplane/Helicopter switch within one setup. Existing specific-aircraft XML imports remain separate selectable layers. |
| Profiles accept specific contexts; the SDK explicitly excludes COCKPIT_CAMERA from Airplane profiles. Unsupported contexts can be ignored by MSFS. | Camera selection opens General automatically while retaining Airplane bindings. The list identifies the editing destination. Actions are not merged into one Airplane XML. |
| Import requires the same controller and matching profile type. | Export setup writes separate XML files and an import guide naming the matching type/device. Setup layers must share controller identity and input format. |
| None/Assigned/Essential filters and text/input searches help locate controls. | All controls is the default. Bound only shows assignments across relevant layers; Find input and Follow navigate between them. Empty searches explain their filters. Guided setup provides a starter list, not a claim to reproduce MSFS's Essential database. |
| Context determines when an assignment operates. Reused inputs can have different purposes. | Conflict warnings remain advisory within each profile/context. They are not a complete runtime assessment of all active layers. |

Sources:

- [Controller Settings FAQ](https://flightsimulator.zendesk.com/hc/en-us/articles/16459737949980-Controller-Settings-FAQ)
- [SDK input profiles, hierarchy and allowed contexts](https://docs.flightsimulator.com/msfs2024/retail/content-configuration/input/input-profiles/)
- [Controller profile import/export](https://flightsimulator.zendesk.com/hc/en-us/articles/21862909046428-How-to-Export-and-Import-your-controller-profiles)

## Workflow exercised

Connect a controller, name its inputs, record a flaps axis in Airplane, switch
to General and record a camera button, then switch back. Both bindings remain
visible in All controls and Bound only. Each layer retains its own name, tuning
and session Undo history. Press-to-find and Follow navigate to the other layer.
A guided sequence can span both types.

Save setup stores all XML layers, the active choice and input aliases in one
`.msfssetup` file for reopening in this app. Export setup produces one native
XML per profile plus alias sidecars and numbered-safe import instructions.
Opening another preset retains existing alternatives; reopening an older setup
preserves the newer working copy. Autosave and startup recovery include inactive
layers. The layout was checked at 1120×680 and the regular window size.

Validation: 56 automated tests, including all 48 public profile fixtures, and
65 actual Tk workflow checks with simulated input streams. The connected
PowerA FlightDeck is enumerated through Windows; its physical inputs were not
manipulated during these automated checks. Local Store saves are read only.

## Remaining acceptance and coverage

Actual MSFS import, active preset selection, model/default assignment, in-flight
behavior and XRAY hardware still require validation. This app does not install
profiles into Store cloud storage. The `.msfssetup` format is for this app;
MSFS imports its exported XML files individually.

New native layers are currently General, Airplane and Helicopter. Other imported
categories and aircraft-specific metadata are preserved; new aircraft model IDs
are not guessed. The context routing uses observed reference categories, not a
claim to reproduce the complete current SDK permission matrix. The SDK is not
installed on this PC, and the bundled action database is not exhaustive.
SDK source editing remains distinct from native Controls-menu import. Package
deployment, image/layout authoring and some proprietary devices are incomplete.
See [FEATURE_MATRIX.md](FEATURE_MATRIX.md) for the wider feature audit.
