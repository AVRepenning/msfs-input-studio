"""Exercise setup, capture failures, navigation and SDK forms in the actual Tk UI.

Physical hardware is enumerated; press/motion streams are simulated for repeatability.
"""
from pathlib import Path
import json
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.profiles import Profile
from msfs_config.sdk import SDKDocument
from msfs_config.sdk_editor import SDKEditor
from msfs_config.drafts import DraftStore


def capture_window(root, path):
    from PIL import ImageGrab
    import ctypes
    root.update()
    api = ctypes.WinDLL('user32.dll')
    api.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    api.GetAncestor.restype = ctypes.c_void_p
    hwnd = api.GetAncestor(root.winfo_id(), 2)
    ImageGrab.grab(window=hwnd).save(path)


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    errors = []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    root.update()
    app.refresh_devices()
    root.update()
    assert app.controller, 'Connect a DirectInput controller for the hardware-backed workflow test.'
    reader, device = app.controller, app.selected_device()
    objects = reader.objects
    buttons = [obj for obj in objects if obj.kind == 'button']
    assert len(buttons) >= 3
    baseline = {o.offset: 0.0 if o.kind == 'axis' else False if o.kind == 'button' else -1 for o in objects}
    checks = []
    def passed(name):
        checks.append(name)
    def action(event):
        app.selected = next(key for key, entry in app.catalogue.actions.items()
                            if key[1] == event and app.profile.category in entry['categories'])
        app.show_action()
        app.refresh_list()
    def poll(values, now):
        with patch.object(reader, 'read', return_value=values), patch('msfs_config.app.time.monotonic', return_value=now):
            app.poll()
    def start(slot='Primary', now=100, values=None):
        with patch.object(reader, 'read', return_value=values or baseline), patch('msfs_config.app.time.monotonic', return_value=now):
            app.start_capture(slot)
    try:
        assert not app.dirty(), 'An untouched new profile must not trigger an unsaved-changes prompt.'
        original = app.profile.to_text()
        app.view_category.set('Helicopter controls')
        app.refresh_list()
        assert any('CYCLIC' in key[1] for key in app.row_ids.values())
        assert app.profile.to_text() == original
        passed('Aircraft browse filter preserves the current profile')
        app.new_profile('Workflow airplane', 'AIRPLANE')
        action('KEY_GEAR_TOGGLE')
        gear = app.selected
        start()
        assert 'LISTENING' in app.capture_title.get()
        assert not app.cancel_button.instate(['disabled'])
        pressed = dict(baseline, **{})
        pressed[buttons[0].offset] = True
        poll(pressed, 100.1)
        assert 'Joystick Button 1' in app.detected_input.get()
        Path('research').mkdir(exist_ok=True)
        with patch.object(reader, 'read', return_value=pressed), patch('msfs_config.app.time.monotonic', return_value=100.1):
            capture_window(root, Path('research/recording-feedback.png'))
        poll(pressed, 100.9)
        assert app.profile.keys(*gear, 'Primary')[0][1] == '0'
        assert 'NOT RECORDING' in app.capture_title.get()
        passed('Listening, countdown, detection and saved feedback')

        before = app.profile.to_text()
        app.search_var.set('no control has this name')
        app.refresh_list()
        assert app.selected is None and all(button.instate(['disabled']) for _, _, button in app.binding_buttons)
        assert app.profile.to_text() == before
        app.clear_browse_filters()
        action('KEY_GEAR_TOGGLE')
        passed('Filtering out the selected action clears the editor and disables hidden edits')

        before = app.profile.to_text()
        start('Secondary', 200)
        poll(baseline, 213)
        assert 'TIMED OUT' in app.capture_title.get()
        assert not app.retry_button.instate(['disabled'])
        assert before == app.profile.to_text()
        start('Secondary', 300, pressed)
        poll(baseline, 300.1)
        poll(pressed, 300.3)
        poll(pressed, 301.1)
        assert app.profile.keys(*gear, 'Secondary')[0][1] == '0'
        passed('Timeout preserves bindings; held button can be released and recorded again')

        # A second button arriving before the settle period extends that period.
        start('Secondary', 350)
        poll(pressed, 350.1)
        chord = dict(pressed)
        chord[buttons[1].offset] = True
        poll(chord, 350.65)
        poll(chord, 350.9)
        assert app.capture is not None
        poll(chord, 351.4)
        assert len(app.profile.keys(*gear, 'Secondary')) == 2
        passed('Slow chords wait for the last detected input before saving')

        app.clear_browse_filters()
        app.refresh_list()
        targets = [key for key in app.row_ids.values() if key[1] in ('KEY_GEAR_TOGGLE', 'KEY_PARKING_BRAKES')]
        assert len(targets) == 2
        held = dict(baseline)
        held[buttons[2].offset] = True
        app.current_values = dict(held)
        app.tree.selection_set([row for row, key in app.row_ids.items() if key in targets])
        with patch.object(reader, 'read', return_value=held), patch('msfs_config.app.time.monotonic', return_value=360):
            app.record_selected()
        values = dict(held)
        values[buttons[0].offset] = True
        poll(values, 360.1)
        poll(values, 360.9)
        assert app.recording['index'] == 1
        poll(held, 361.1)
        poll(held, 361.6)
        assert app.capture is not None and app.recording['index'] == 1
        app.cancel_capture()
        app.selected = gear
        app.show_action()
        passed('Guided recording advances while an unrelated switch remains held')

        unknown = next((o for o in buttons if app.resolve_input(o.msfs_name()) is None), None)
        if unknown:
            before = app.profile.to_text()
            start('Secondary', 400)
            values = dict(baseline)
            values[unknown.offset] = True
            poll(values, 400.1)
            poll(values, 400.9)
            assert 'ID NEEDED' in app.capture_title.get()
            assert before == app.profile.to_text()
            passed('Unknown input is visibly detected without writing a guessed ID')
        app.cancel_capture()
        start('Secondary', 450)
        app.root.event_generate('<Escape>')
        root.update()
        assert app.capture is None and 'NOT RECORDING' in app.capture_title.get()
        passed('Escape cancellation')

        app.search_var.set('nothing can match this text')
        app.context_var.set('MODE_PAUSE')
        app.view_category.set('Helicopter controls')
        app.unbound_only.set(True)
        app.conflicts_only.set(True)
        with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=500):
            app.find_input()
        poll(pressed, 500.1)
        poll(pressed, 500.9)
        assert app.selected == gear
        assert app.tree.focus() in app.tree.selection()
        assert not app.search_var.get() and not app.unbound_only.get()
        root.update()
        assert 'INPUT FOUND' in app.capture_title.get()
        assert app.tree.bbox(app.tree.focus()), 'The selected input assignment must remain visible after panel layout changes.'
        passed('Input search resets hiding filters and jumps to the binding')

        app.clear_input_filter()
        app.selected = gear
        app.bind('Secondary', [app.resolve_input('Joystick Button 2')])
        app.jump_to_names(['Joystick Button 1', 'Joystick Button 2'])
        assert not app.tree.get_children(), 'Primary and secondary must not be merged into a false chord.'
        assert app.selected is None
        assert all(button.instate(['disabled']) for _, _, button in app.binding_buttons)
        passed('Search respects separate binding slots and clears stale action on no match')

        app.clear_input_filter()
        action('KEY_PARKING_BRAKES')
        parking = app.selected
        app.bind('Primary', [app.resolve_input('Joystick Button 3')])
        app.follow_input.set(True)
        app.current_values = dict(baseline)
        app.toggle_follow()
        poll(pressed, 600)
        poll(pressed, 600.5)
        assert app.selected == gear
        poll(baseline, 601)
        other = dict(baseline)
        other[buttons[2].offset] = True
        poll(other, 602)
        poll(other, 602.5)
        assert app.selected == parking and app.follow_input.get()
        root.update()
        assert app.follow_input.get(), 'A programmatic selection must not stop follow mode.'
        app.cancel_capture()
        passed('Follow controller supports successive searches')

        app.clear_input_filter()
        action('KEY_AXIS_AILERONS_SET')
        aileron = app.selected
        pair = app.resolve_input('Joystick L-Axis X+')
        assert pair
        app.bind('Primary', [pair])
        app.jump_to_names(['Joystick L-Axis X'])
        assert aileron in app.row_ids.values()
        passed('Physical axis search includes split-axis assignments')

        action('KEY_AXIS_AILERONS_SET')
        axes = [obj for obj in objects if obj.kind == 'axis']
        start('Secondary', 650)
        diagonal = dict(baseline)
        diagonal[axes[0].offset], diagonal[axes[1].offset] = .7, .3
        poll(diagonal, 650.1)
        poll(diagonal, 650.9)
        assert len(app.profile.keys(*aileron, 'Secondary')) == 1
        assert app.profile.keys(*aileron, 'Secondary')[0][0].strip() == axes[0].msfs_name()
        passed('Diagonal stick movement captures the dominant axis without a false chord')

        with tempfile.TemporaryDirectory() as folder:
            app.drafts = DraftStore(folder)
            app.save_draft()
            rows = app.drafts.entries()
            assert len(rows) == 1 and rows[0]['profile'].to_text() == app.profile.to_text()
            saved = app.profile.to_text()
            window = app.draft_browser()
            app.profile.name = 'Temporary unsaved name'
            with patch('msfs_config.app.messagebox.askyesnocancel', return_value=False):
                def open_button(widget):
                    for child in widget.winfo_children():
                        if isinstance(child, __import__('tkinter.ttk', fromlist=['Button']).Button) and child.cget('text') == 'Open selected working copy':
                            child.invoke()
                            return True
                        if open_button(child):
                            return True
                    return False
                assert open_button(window)
            assert app.profile.to_text() == saved
            assert 'WORKING COPY OPENED' in app.capture_title.get()
            app.drafts = DraftStore(storage=False)
        passed('Autosaved working copy can be resumed through the UI')

        app.clear_input_filter()
        app.selected = gear
        app.refresh_list()
        before = app.profile.to_text()
        rows = [row for row, identity in app.row_ids.items() if identity in (gear, parking)]
        app.tree.selection_set(rows)
        app.clear_selected()
        assert not app.profile.keys(*gear, 'Primary') and not app.profile.keys(*parking, 'Primary')
        app.undo()
        assert app.profile.to_text() == before
        assert len(app.history_labels) == len(app.history)
        passed('Batch clear and named undo restore both bindings')

        document = SDKDocument.device_config(device, app.labels, app.catalogue)
        assert not document.validate()
        editor = SDKEditor(app, document)
        root.update()
        node = document.root.find('Device')
        node.set('FutureAttribute', 'keep')
        editor.refresh(node)
        editor.fields[('attribute', 'DisplayName')].set('My named controller')
        editor.apply()
        assert node.get('DisplayName') == 'My named controller'
        assert node.get('FutureAttribute') == 'keep'
        editor.undo()
        assert editor.document.root.find('Device').get('DisplayName') != 'My named controller'
        editor.redo()
        assert editor.document.root.find('Device').get('DisplayName') == 'My named controller'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'DeviceConfig.xml'
            with patch('msfs_config.sdk_editor.filedialog.asksaveasfilename', return_value=str(path)):
                editor.save()
            assert SDKDocument.load(path).root.find('Device').get('FutureAttribute') == 'keep'
        editor.saved = editor.document.to_text()
        editor.close()
        passed('SDK forms, history and source export preserve unknown fields')

        # Verify a real exported file and record the actual visible controller UI.
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'workflow.xml'
            with patch('msfs_config.app.filedialog.asksaveasfilename', return_value=str(path)):
                assert app.save_profile()
            assert not Profile.load(path).validate()
        passed('Offline XML export passes validation')
        screenshots = Path('research')
        screenshots.mkdir(exist_ok=True)
        app.tabs.select(app.monitor_page)
        with patch.object(reader, 'read', return_value=baseline):
            root.update()
            capture_window(root, screenshots / 'controller-test.png')
        assert len(app.dashboard.button_regions) == len(buttons)
        app.dashboard.button_canvas.event_generate('<Button-1>', x=30, y=43)
        root.update()
        assert app.monitor.selection() == (str(buttons[0].offset),)
        app.input_label_var.set('Gear lever')
        app.set_input_label()
        assert app.labels.get(device.instance_guid, buttons[0].msfs_name()) == 'Gear lever'
        passed('Numbered button grid selection and input naming')
        root.geometry('1120x740')
        with patch.object(reader, 'read', return_value=baseline):
            capture_window(root, screenshots / 'controller-test-small.png')
        assert app.dashboard.button_canvas.winfo_height() >= 58 and app.dashboard.canvas.winfo_height() >= 58
        passed('Controller indicators remain available in the minimum window size')
        window, dashboard = app.controller_test_window()
        with patch.object(reader, 'read', return_value=baseline):
            capture_window(window, screenshots / 'controller-test-popup.png')
        assert len(dashboard.button_regions) == len(buttons)
        assert sum(region[-1].kind == 'axis' for region in dashboard.hit_regions) == sum(o.kind == 'axis' for o in objects)
        window.destroy()
        passed('Dedicated test window exposes every enumerated axis and button')
        assert not errors, 'Tk callback errors: ' + repr(errors)
        result = {'checks': checks, 'passed': len(checks), 'callback_errors': errors,
                  'hardware': device.name, 'axes': sum(o.kind == 'axis' for o in objects), 'buttons': len(buttons),
                  'input_stream': 'simulated; hardware enumerated through Windows',
                  'screenshots': ['research/controller-test.png', 'research/controller-test-small.png', 'research/controller-test-popup.png']}
        (screenshots / 'workflow-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.saved_text = app.profile.to_text() if app.profile else None
        app.close()


if __name__ == '__main__':
    main()
