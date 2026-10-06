"""Walk through one controller setup with General and aircraft layers in the real UI."""
from pathlib import Path
import json
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.profiles import Profile
from msfs_config.setups import ControllerSetup, SetupStore
from qa_workflow import capture_window


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    errors, checks = [], []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    output = Path('research')
    output.mkdir(exist_ok=True)
    try:
        root.update()
        app.refresh_devices()
        reader = app.controller
        assert reader, 'Connect a controller for the setup workflow.'
        baseline = {obj.offset: 0.0 if obj.kind == 'axis' else False if obj.kind == 'button' else -1 for obj in reader.objects}
        axis = next(obj for obj in reader.objects if obj.kind == 'axis')
        buttons = [obj for obj in reader.objects if obj.kind == 'button']
        flaps, camera = ('AIRCRAFT', 'KEY_AXIS_FLAPS_SET'), ('MODES', 'KEY_COCKPIT_RESET')
        stamp = time.monotonic()

        def choose(category):
            app.type_var.set(category + ' controls')
            app.category_combo.event_generate('<<ComboboxSelected>>')
            with patch.object(reader, 'read', return_value=baseline):
                root.update()
            assert app.profile.category == category.upper()

        def record(action, obj, value, now):
            app.selected = action
            app.show_action()
            app.refresh_list()
            with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=now):
                app.start_capture('Primary')
            moved = dict(baseline)
            moved[obj.offset] = value
            for tick in (now + .1, now + .9):
                with patch.object(reader, 'read', return_value=moved), patch('msfs_config.app.time.monotonic', return_value=tick):
                    app.poll()
            assert app.capture is None and app.profile.keys(*action, 'Primary')

        app.new_profile('Commercial Airbus', 'AIRPLANE')
        app.profile.set_axis(axis.axis, {'AxisDeadZone': '9'})
        record(flaps, axis, .85, stamp)
        airplane_xml = app.profile.to_text()
        airplane_layer = app.setup.active
        setup_id = app.setup.id
        choose('General')
        assert app.setup.id == setup_id and len(app.setup.layers) == 2
        assert airplane_layer.profile.to_text() == airplane_xml
        assert not any(isinstance(child, tk.Toplevel) for child in root.winfo_children())
        checks.append('General/Airplane selector switches within one setup without a New or export prompt')
        record(camera, buttons[0], True, stamp + 2)
        app.name_var.set('FlightDeck cameras')
        app.profile.set_axis(axis.axis, {'AxisDeadZone': '11'})
        general_xml = app.profile.to_text()
        general_layer = app.setup.active
        choose('Airplane')
        assert app.profile.to_text() == airplane_xml
        camera_row = next(row for row, identity in app.row_ids.items() if identity == camera)
        assert app.tree.set(camera_row, 'binding') != '—'
        assert app.tree.set(camera_row, 'scope') == 'General'
        app.bound_only.set(True)
        app.refresh_list()
        assert camera in app.row_ids.values() and flaps in app.row_ids.values()
        app.bound_only.set(False)
        app.refresh_list()
        checks.append('All controls and Bound only display existing General and airplane bindings together')
        app.undo()
        assert not app.profile.keys(*flaps, 'Primary')
        assert general_layer.profile.to_text() == general_xml
        app.redo()
        assert app.profile.to_text() == airplane_xml
        choose('General')
        assert app.profile.to_text() == general_xml
        assert app.profile.device.find(f'Axes/Axis[@AxisName="{axis.axis}"]').get('AxisDeadZone') == '11'
        checks.append('Bindings, names, tuning and Undo/Redo stay independent and survive repeated layer switching')
        choose('Helicopter')
        helicopter_layer = app.setup.active
        assert len(app.setup.layers) == 3 and helicopter_layer.profile.category == 'HELICOPTER'
        choose('Airplane')
        assert app.profile.to_text() == airplane_xml
        checks.append('Helicopter is another retained layer rather than a replacement for airplane or camera controls')

        app.search_var.set('reset cockpit')
        app.view_category.set('All controls')
        app.refresh_list()
        row = next(row for row, identity in app.row_ids.items() if identity == camera)
        assert app.tree.set(row, 'scope') == 'General'
        app.tree.selection_set(row)
        app.tree.focus(row)
        app.select_action()
        assert app.profile.category == 'GENERAL' and app.selected == camera
        assert app.search_var.get() == 'reset cockpit'
        assert airplane_layer.profile.to_text() == airplane_xml
        checks.append('Selecting a camera control automatically edits General, preserves the search, and shows its storage layer')
        choose('Airplane')
        app.jump_to_names([buttons[0].msfs_name()])
        assert app.profile.category == 'GENERAL' and app.selected == camera
        checks.append('Press-to-find searches other setup profiles and navigates to the camera binding')
        app.follow_input.set(True)
        app.jump_to_names([axis.msfs_name()])
        assert app.profile.category == 'AIRPLANE' and app.selected == flaps and app.follow_input.get()
        app.jump_to_names([buttons[0].msfs_name()])
        assert app.profile.category == 'GENERAL' and app.follow_input.get()
        app.cancel_capture()
        checks.append('Follow controller remains enabled while jumping between General and aircraft bindings')

        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            app.setup_store = SetupStore(folder / 'working')
            app.labels.set(app.label_guid(app.profile.device.attrib), buttons[0].msfs_name(), 'Camera reset')
            saved_path = folder / 'Controller.msfssetup'
            with patch('msfs_config.app.filedialog.asksaveasfilename', return_value=str(saved_path)):
                assert app.save_setup()
            saved, labels = ControllerSetup.load(saved_path)
            assert len(saved.layers) == 3 and saved.active.profile.category == 'GENERAL'
            assert any('Camera reset' in values.values() for values in labels.values())
            checks.append('One portable setup file saves every layer, active selection and controller input names')
            app.name_var.set('Unsaved camera edits')
            unsaved_xml = app.profile.to_text()
            old = app.setup
            with patch('msfs_config.app.filedialog.askopenfilename', return_value=str(saved_path)):
                app.open_setup()
            assert app.profile.to_text() == general_xml
            assert old is not app.setup and old.active.profile.to_text() == unsaved_xml
            assert old.id in app.setups and old.id != app.setup.id
            assert len(app.setup_store.entries()) >= 1
            checks.append('Reopening a saved setup restores all layers and retains newer unsaved edits as another working copy')
            export_folder = folder / 'export'
            export_folder.mkdir()
            with patch('msfs_config.app.filedialog.askdirectory', return_value=str(export_folder)):
                files = app.export_setup()
            assert len(files) == 3
            profiles = {Profile.load(path).category: Profile.load(path) for path in files}
            assert profiles['GENERAL'].keys(*camera, 'Primary')
            assert profiles['AIRPLANE'].keys(*flaps, 'Primary')
            assert flaps not in profiles['GENERAL'].actions() and camera not in profiles['AIRPLANE'].actions()
            assert (export_folder / 'IMPORT-SETUP.txt').is_file()
            assert list(export_folder.glob('*.studio.json'))
            checks.append('Export setup creates separate valid XML profiles, input-name sidecars and an import guide for one controller')
            airplane_saved = app.setup.category('AIRPLANE').profile.to_text()
            choose('General')
            app.duplicate()
            assert len(app.setup.layers) == 4
            assert app.setup.category('AIRPLANE').profile.to_text() == airplane_saved
            assert len([layer for layer in app.setup.layers if layer.profile.category == 'GENERAL']) == 2
            original_label = next(label for label, target in app.layer_choices.items() if target == ('layer', app.setup.layers[1].id))
            app.type_var.set(original_label)
            app.category_changed()
            assert app.profile.to_text() == general_xml
            checks.append('Duplicated presets remain selectable alternatives and keep the original plus other layers intact')
            imported = Profile.new('Imported Airplane preset', dict(app.profile.device.attrib), 'AIRPLANE')
            path = folder / 'import.xml'
            imported.save(path)
            with patch('msfs_config.app.filedialog.askopenfilename', return_value=str(path)):
                app.open_profile()
            assert len(app.setup.layers) == 5
            assert any(layer.profile.to_text() == airplane_saved for layer in app.setup.layers)
            checks.append('Importing another XML adds a preset to the same setup without dropping existing airplane or camera edits')
            app.save_setup_cache()
            entries = app.setup_store.entries()
            recovered = next(row['setup'] for row in entries if row['setup'].id == app.setup.id)
            assert len(recovered.layers) == 5
            assert any(layer.profile.keys(*camera, 'Primary') for layer in recovered.layers)
            assert any(layer.profile.keys(*flaps, 'Primary') for layer in recovered.layers)
            checks.append('Local autosave recovery includes inactive layers and their bindings')
            recovery_window = tk.Tk()
            with patch('tkinter._default_root', recovery_window):
                restored = App(recovery_window, user_library=False)
            restored.setup_store = app.setup_store
            try:
                recovery_window.update()
                if restored.setup is None:
                    restored.refresh_devices()
                assert restored.setup, (restored.status.get(), restored.device_summary.cget('text'))
                assert restored.setup.id == app.setup.id and len(restored.setup.layers) == 5
                assert any(layer.profile.keys(*camera, 'Primary') for layer in restored.setup.layers)
                assert any(layer.profile.keys(*flaps, 'Primary') for layer in restored.setup.layers)
                assert restored.capture_title.get() == 'SETUP RECOVERED'
                checks.append('Starting again with the controller restores the entire most recent setup automatically')
            finally:
                with patch.object(restored, 'can_discard', return_value=True):
                    restored.close()
            app.setup_store = SetupStore(False)

        # Guided recording may include actions from General and aircraft layers.
        reader = app.controller
        app.new_profile('Guided controller', 'AIRPLANE')
        app.refresh_list()
        rows = [row for row, identity in app.row_ids.items() if identity in (camera, flaps)]
        app.tree.selection_set(rows)
        with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=stamp + 10):
            app.record_selected()
        assert app.recording and len(app.recording['targets']) == 2
        for index in range(2):
            now = stamp + 10 + index * 2
            moved = dict(baseline)
            moved[buttons[index + 1].offset] = True
            for tick in (now + .1, now + .9):
                with patch.object(reader, 'read', return_value=moved), patch('msfs_config.app.time.monotonic', return_value=tick):
                    app.poll()
            with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=now + 1):
                app.record_next()
        assert not app.recording, (app.recording['index'], app.capture, app.capture_title.get())
        assert app.setup.category('GENERAL').profile.keys(*camera, 'Primary')
        assert app.setup.category('AIRPLANE').profile.keys(*flaps, 'Primary')
        checks.append('One guided recording session can assign General and airplane actions to their correct XML layers')
        with patch.object(reader, 'read', return_value=baseline):
            capture_window(root, output / 'controller-setup-layers.png')
        root.geometry('1120x680')
        capture_window(root, output / 'controller-setup-minimum.png')
        def buttons(widget):
            return [widget] if isinstance(widget, ttk.Button) else [button for child in widget.winfo_children() for button in buttons(child)]
        controls = {button.cget('text'): button for button in buttons(root)}
        for label in ('New setup', 'Save setup', 'MSFS presets', 'Export setup'):
            button = controls[label]
            assert button.winfo_ismapped() and button.winfo_width() >= button.winfo_reqwidth()
            assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width(), label
        checks.append('New, save, simulator presets and export remain fully accessible at the minimum window size')
        assert not errors, errors
        result = {'passed': len(checks), 'checks': checks, 'callback_errors': errors,
                  'input_stream': 'simulated axis/button motion; real Windows controller enumeration'}
        (output / 'setup-workflow-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        with patch.object(app, 'can_discard', return_value=True):
            app.close()


if __name__ == '__main__':
    main()
