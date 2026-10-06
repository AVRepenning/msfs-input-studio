"""Test real keyboard/mouse backends with simulated capture streams and local references.

The scan reads Store XML copies. No local bindings or identities are written to QA artifacts.
"""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.catalogue import device_family
from msfs_config.local_profiles import scan_profiles
from msfs_config.profiles import Profile
from msfs_config.system_inputs import SystemDevice


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    errors, checks = [], []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    try:
        root.update()
        app.saved_profiles = scan_profiles()
        for row in app.saved_profiles:
            app.catalogue.learn(row['profile'])
        app.refresh_devices()
        def choose(family):
            app.saved_text = app.profile.to_text()
            index = next(i for i, device in enumerate(app.devices) if isinstance(device, SystemDevice) and device.family == family)
            app.device_combo.current(index)
            app.select_device()
            app.new_profile('QA ' + family, 'AIRPLANE')
            assert app.controller_matches()
            return app.controller
        def action(event):
            app.selected = next(key for key, entry in app.catalogue.actions.items() if key[1] == event and 'AIRPLANE' in entry['categories'])
            app.show_action()
            app.refresh_list()
            return app.selected
        def poll(reader, values, now):
            with patch.object(reader, 'read', return_value=values), patch('msfs_config.app.time.monotonic', return_value=now):
                app.poll()
        def start(reader, values, now):
            with patch.object(reader, 'read', return_value=values), patch('msfs_config.app.time.monotonic', return_value=now):
                app.start_capture('Primary')
        keyboard = choose('keyboard')
        key_count = len(keyboard.read())
        gear = action('KEY_GEAR_TOGGLE')
        baseline = {obj.offset: False for obj in keyboard.objects}
        start(keyboard, baseline, 100)
        values = dict(baseline, **{})
        values[162] = True
        poll(keyboard, values, 100.1)
        values[82] = True
        poll(keyboard, values, 100.5)
        poll(keyboard, values, 101.3)
        assert {int(value) for _, value in app.profile.keys(*gear, 'Primary')} == {162, 82}
        assert int(app.profile.action(*gear).get('Flag')) & 16
        checks.append('Keyboard Ctrl+R capture preserves keys and modifier flags')
        # Imports may store the modifier in Flag, without a separate KEY node.
        app.profile.set_binding(*gear, 'Primary', [app.resolve_input('r')])
        app.profile.action(*gear).set('Flag', '18')
        app.jump_to_names(['CTRL', 'r'])
        assert gear in app.row_ids.values()
        checks.append('Physical chord search finds imported flag-only modifiers')
        app.clear_input_filter()
        parking = action('KEY_PARKING_BRAKES')
        app.bind('Primary', [app.resolve_input('.')])
        app.jump_to_names(['.'])
        assert parking in app.row_ids.values()
        app.jump_to_names(['-'])
        assert parking not in app.row_ids.values()
        checks.append('Keyboard punctuation searches do not collide')
        app.clear_input_filter()
        action('KEY_GEAR_TOGGLE')
        app.record_escape.set(True)
        start(keyboard, baseline, 200)
        app.escape(None)
        assert app.capture is not None
        values = dict(baseline)
        values[27] = True
        poll(keyboard, values, 200.1)
        poll(keyboard, values, 200.9)
        assert app.profile.keys(*gear, 'Primary')[0][1] == '27'
        app.record_escape.set(False)
        checks.append('Optional Escape recording binds Escape without cancelling')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'keyboard.xml'
            with patch('msfs_config.app.filedialog.asksaveasfilename', return_value=str(path)):
                assert app.save_profile()
            assert not Profile.load(path).validate()
            assert Profile.load(path).device.get('GUID') == '{0}'
        checks.append('Native keyboard identity exports without inventing a UUID')
        mouse = choose('mouse')
        assert len(mouse.read()) == len(mouse.objects)
        gear = action('KEY_GEAR_TOGGLE')
        baseline = {obj.offset: 0 for obj in mouse.objects}
        start(mouse, baseline, 300)
        mouse.wheel(120)
        raw = mouse.read()
        assert raw[5] and not raw[6]
        assert not mouse.read()[5]
        values = dict(baseline)
        values[5] = True
        poll(mouse, values, 300.1)
        poll(mouse, baseline, 300.9)
        assert app.profile.keys(*gear, 'Primary')[0][1] == '5'
        checks.append('Mouse wheel pulses survive release and become verified bindings')
        action('KEY_AXIS_AILERONS_SET')
        start(mouse, baseline, 400)
        values = dict(baseline)
        values[7] = .5
        poll(mouse, values, 400.1)
        poll(mouse, values, 400.9)
        assert app.profile.keys(*app.selected, 'Primary')[0][1] == '11'
        assert int(app.profile.action(*app.selected).get('Flag')) & 4
        checks.append('Mouse motion capture uses observed full-axis input IDs')
        app.clear_browse_filters()
        root.update()
        assert not errors, repr(errors)
        result = {'passed': len(checks), 'checks': checks, 'keyboard_objects': key_count,
                  'mouse_objects': len(mouse.objects), 'callback_errors': errors,
                  'input_stream': 'simulated; native readers and Store references inspected'}
        Path('research/system-workflow-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.saved_text = app.profile.to_text() if app.profile else None
        with patch.object(app, 'can_discard', return_value=True):
            app.close()


if __name__ == '__main__':
    main()
