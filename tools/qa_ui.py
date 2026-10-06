"""Exercise the actual Windows UI, export path and undo history; save an app screenshot."""
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.profiles import Profile


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    root.update()
    app.refresh_devices()
    root.update()
    devices = list(app.devices)
    device = app.selected_device()
    identity = device.attributes if device else {'DeviceName': 'QA controller', 'GUID': '{12345678-1234-1234-1234-123456789abc}', 'ProductID': '42', 'CompositeID': '0', 'HWVer': '1'}
    app.profile = Profile.new('My airplane controls', identity, 'AIRPLANE', ['X'])
    app.saved_text = app.profile.to_text()
    app.sync_profile()
    app.search_var.set('aileron')
    app.refresh_list()
    rows = len(app.tree.get_children())
    assert rows > 0
    app.selected = next(key for key, entry in app.catalogue.actions.items()
                        if key[1] == 'KEY_AXIS_AILERONS_SET' and 'AIRPLANE' in entry['categories'])
    app.show_action()
    app.bind('Primary', [app.catalogue.resolve('Joystick L-Axis X')])
    assert int(app.profile.action(*app.selected).get('Flag')) & 4
    app.manual_binding  # callable GUI command exists
    app.bind('Secondary', [app.catalogue.resolve('Joystick Button 1'), app.catalogue.resolve('Joystick Button 2')])
    app.axis_scope.set('Primary override')
    app.load_axis()
    app.axis_values['AxisDeadZone'].set('8')
    app.apply_axis()
    assert app.profile.action(*app.selected).find('Primary/Axis').get('AxisDeadZone') == '8'
    assert int(app.profile.action(*app.selected).get('Flag')) & 4096
    app.undo()
    assert app.profile.action(*app.selected).find('Primary/Axis') is None
    app.redo()
    assert app.profile.action(*app.selected).find('Primary/Axis').get('AxisDeadZone') == '8'
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'airplane.xml'
        with patch('msfs_config.app.filedialog.asksaveasfilename', return_value=str(path)):
            assert app.save_profile()
        exported = Profile.load(path)
        assert exported.category == 'AIRPLANE'
        assert len(exported.keys(*app.selected, 'Secondary')) == 2
        assert not app.dirty()
    # Rename a real Windows input, then verify aliases never replace MSFS IDs.
    if app.controller:
        buttons = [o for o in app.controller.objects if o.kind == 'button']
        first, second = buttons[:2]
        app.monitor.selection_set(str(first.offset))
        app.input_label_var.set('Landing gear')
        app.set_input_label()
        assert app.labels.get(device.instance_guid, first.msfs_name()) == 'Landing gear'
        rendered = next(name for name in app.input_choice_names if name.startswith('Landing gear ·'))
        app.input_vars['Primary'].set(rendered)
        app.manual_binding('Primary')
        assert app.profile.keys(*app.selected, 'Primary')[0][0].strip() == first.msfs_name()
        assert 'Landing gear' not in app.profile.to_text()

        # Drive the same poll/capture/advance path used by the real recording UI.
        targets = [key for key, entry in app.catalogue.actions.items()
                   if key[1] in ('KEY_GEAR_TOGGLE', 'KEY_PARKING_BRAKES') and 'AIRPLANE' in entry['categories']][:2]
        assert len(targets) == 2
        app.search_var.set('')
        app.refresh_list()
        rows_to_record = [row for row, identity in app.row_ids.items() if identity in targets]
        baseline = {o.offset: 0.0 if o.kind == 'axis' else False if o.kind == 'button' else -1
                    for o in app.controller.objects}
        app.current_values = dict(baseline)
        with patch.object(app.controller, 'read', return_value=baseline):
            app.tree.selection_set(rows_to_record)
            app.record_selected()
        assert app.recording and len(app.recording['targets']) == 2
        guided_targets = list(app.recording['targets'])
        def poll_at(values, seconds):
            with patch.object(app.controller, 'read', return_value=values), patch('msfs_config.app.time.monotonic', return_value=seconds):
                app.poll()
        for index, obj in enumerate((first, second)):
            pressed = dict(baseline)
            pressed[obj.offset] = True
            now = 1000 + index * 5
            poll_at(pressed, now)
            poll_at(pressed, now + .9)
            assert app.recording['index'] == index + 1
            poll_at(baseline, now + 1.2)
            poll_at(baseline, now + 1.7)
        assert app.recording is None
        assert app.profile.keys(*guided_targets[0], 'Primary')[0][0].strip() == first.msfs_name()
        assert app.profile.keys(*guided_targets[1], 'Primary')[0][0].strip() == second.msfs_name()
        # A named profile carries its labels in a sidecar while XML stays native.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'with-labels.xml'
            with patch('msfs_config.app.filedialog.asksaveasfilename', return_value=str(path)):
                assert app.save_profile()
            assert path.with_suffix('.studio.json').is_file()
            assert 'Landing gear' not in path.read_text(encoding='utf-8')
    app.search_var.set('')
    app.refresh_list()
    root.update_idletasks()
    # Capture the application itself; no full-desktop capture or unrelated windows.
    root.lift()
    root.update()
    root.after(600, lambda: finish(root, app, devices, rows))
    root.mainloop()


def finish(root, app, devices, rows):
    from tools.qa_workflow import capture_window
    screenshot = Path('research/ui-preview.png')
    screenshot.parent.mkdir(exist_ok=True)
    capture_window(root, screenshot)
    results = {'gui_commands': 'passed', 'search_rows': rows,
               'devices': [d.name for d in devices],
               'live_objects': len(app.controller.objects) if app.controller else 0,
               'xml_export': 'passed', 'axis_override': 'passed', 'undo_redo': 'passed',
               'guided_recording': 'passed' if devices else 'not tested without hardware',
               'input_labels': 'passed' if devices else 'not tested without hardware',
               'screenshot': str(screenshot)}
    Path('research/ui-qa.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    app.saved_text = app.profile.to_text()
    with patch.object(app, 'can_discard', return_value=True):
        app.close()
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
