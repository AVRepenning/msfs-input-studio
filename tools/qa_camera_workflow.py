"""Reproduce hidden camera controls and walk through configuring a camera binding."""
from pathlib import Path
import json
import sys
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.profiles import Profile
from qa_workflow import capture_window
from qa_saved_workflow import widgets


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    checks, errors = [], []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    output = Path('research')
    output.mkdir(exist_ok=True)
    try:
        root.update()
        app.refresh_devices()
        reader = app.controller
        assert reader, 'Connect a controller for the camera capture workflow.'
        app.new_profile('Commercial Airbus Flaps', 'AIRPLANE')
        flaps = ('AIRCRAFT', 'KEY_AXIS_FLAPS_SET')
        axis = next(obj for obj in reader.objects if obj.kind == 'axis')
        pair = app.catalogue.resolve(axis.msfs_name(), 'joystick')
        app.profile.set_binding(*flaps, 'Primary', [pair])
        expected_profile = app.profile.to_text()
        camera_rows = {identity for identity, entry in app.catalogue.actions.items()
                       if App.action_group_name(entry) == 'Camera / views'}
        assert len(camera_rows) == 470
        assert any(app.catalogue.actions[key].get('group') == 'Camera' for key in camera_rows)
        assert any(not app.catalogue.actions[key].get('group') for key in camera_rows)
        app.action_group.set('Camera / views')
        app.refresh_list()
        root.update()
        assert not app.row_ids
        assert app.empty_results.winfo_ismapped()
        assert 'General' in app.empty_results_detail.cget('text')
        assert '470' in app.empty_results_detail.cget('text')
        capture_window(root, output / 'camera-hidden-explanation.png')
        checks.append('Airplane camera filter explains the 470 General controls hidden by profile type')
        app.show_other_profiles_button.invoke()
        root.update()
        assert set(app.row_ids.values()) == camera_rows
        assert app.action_group.get() == 'Camera / views'
        assert app.profile.to_text() == expected_profile
        assert 'Camera' not in app.group_combo.cget('values')
        checks.append('Show matching controls reveals both camera source groups and preserves the airplane bindings')
        app.search_var.set('cockpit')
        app.refresh_list()
        subset = set(app.row_ids.values())
        app.view_category.set('Current profile')
        app.refresh_list()
        app.show_other_profiles_button.invoke()
        assert app.search_var.get() == 'cockpit' and set(app.row_ids.values()) == subset
        checks.append('Showing hidden controls preserves the search and selected group')
        app.selected = next(key for key in subset if key[1] == 'KEY_COCKPIT_RESET')
        app.show_action()
        assert app.profile_hint_button.cget('text') == 'New General profile'
        app.profile_hint_button.invoke()
        root.update()
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        assert app.profile.to_text() == expected_profile
        assert any(isinstance(widget, ttk.Combobox) and widget.get() == 'General controls' for widget in widgets(dialog))
        create = next(widget for widget in widgets(dialog) if isinstance(widget, ttk.Button) and widget.cget('text') == 'Create profile')
        with patch.object(app, 'can_discard', return_value=True):
            create.invoke()
        assert app.profile.category == 'GENERAL' and flaps not in app.profile.actions()
        checks.append('Camera selection offers a separate General profile without reclassifying existing flaps bindings')
        app.action_group.set('Camera / views')
        app.refresh_list()
        assert set(app.row_ids.values()) == camera_rows
        app.selected = next(key for key in camera_rows if key[1] == 'KEY_COCKPIT_RESET')
        camera = app.selected
        app.show_action()
        get_input = next(button for slot, label, button in app.binding_buttons if slot == 'Primary' and label == 'Get Input')
        assert not get_input.instate(['disabled'])
        baseline = {obj.offset: 0.0 if obj.kind == 'axis' else False if obj.kind == 'button' else -1 for obj in reader.objects}
        button = next(obj for obj in reader.objects if obj.kind == 'button')
        with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=100):
            get_input.invoke()
        pressed = dict(baseline)
        pressed[button.offset] = True
        for now in (100.1, 100.9):
            with patch.object(reader, 'read', return_value=pressed), patch('msfs_config.app.time.monotonic', return_value=now):
                app.poll()
        assert app.profile.keys(*app.selected, 'Primary')[0][0] == button.msfs_name()
        exported = Profile.from_text(app.profile.to_text())
        assert exported.category == 'GENERAL' and not exported.validate()
        capture_window(root, output / 'camera-binding-recorded.png')
        checks.append('Camera button recording is enabled in General and produces valid General-profile XML')
        app.search_var.set('a control that does not exist')
        app.refresh_list()
        root.update()
        assert not app.row_ids and app.empty_results.winfo_ismapped()
        assert app.empty_results_title.cget('text') == 'No controls match these filters'
        assert not app.show_other_profiles_button.winfo_ismapped()
        checks.append('A search with no matching control shows filter guidance instead of suggesting the wrong profile')
        app.clear_filters_button.invoke()
        app.refresh_list()
        root.update()
        assert app.row_ids and not app.empty_results.winfo_ismapped()
        assert app.profile.keys(*camera, 'Primary') == exported.keys(*camera, 'Primary')
        checks.append('Clear filters restores the list without changing the recorded binding')
        app.action_group.set('Camera / views')
        app.context_var.set('COCKPIT_CAMERA')
        app.bound_only.set(True)
        app.unbound_only.set(True)
        app.refresh_list()
        assert not app.row_ids and app.empty_results_title.cget('text') == 'No controls match these filters'
        app.clear_filters_button.invoke()
        app.refresh_list()
        assert app.row_ids and not app.bound_only.get() and not app.unbound_only.get()
        checks.append('Conflicting bound/unbound filters can be reset through the empty-state action')
        assert not errors, errors
        result = {'passed': len(checks), 'checks': checks, 'camera_controls': len(camera_rows), 'callback_errors': errors,
                  'input_stream': 'simulated button press; real Windows controller enumeration'}
        (output / 'camera-workflow-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.saved_text = app.profile.to_text() if app.profile else None
        app.close()


if __name__ == '__main__':
    main()
