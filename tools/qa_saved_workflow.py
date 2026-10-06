"""Reproduce Saved responsiveness and General-to-Flaps setup in the actual UI."""
from pathlib import Path
import json
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config.app import App
from msfs_config.local_profiles import scan_profiles
from msfs_config.profiles import Profile
from qa_workflow import capture_window


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def main():
    root = tk.Tk()
    app = App(root, user_library=False)
    errors, checks = [], []
    root.report_callback_exception = lambda kind, value, tb: errors.append(str(value))
    output = Path('research')
    output.mkdir(exist_ok=True)

    def pump_until(condition, timeout=10):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            root.update()
            time.sleep(.005)
        root.update()
        assert condition(), 'UI condition timed out'

    try:
        root.update()
        app.refresh_devices()
        assert app.controller, 'Connect a controller for the Flaps recording check.'
        reader = app.controller
        identity = dict(app.profile.device.attrib)
        app.profile.name = 'Commercial Airbus Flaps'
        app.name_var.set(app.profile.name)
        app.profile.device.find('Axes/Axis').set('AxisDeadZone', '9')
        app.view_category.set('All controls')
        app.search_var.set('Flaps')
        app.selected = ('AIRCRAFT', 'KEY_AXIS_FLAPS_SET')
        app.refresh_list()
        app.show_action()
        root.update()
        assert app.profile.category == 'GENERAL'
        assert app.profile_hint.winfo_ismapped()
        assert 'Airplane or Helicopter' in app.profile_hint_text.cget('text')
        assert app.profile_hint_button.cget('text') == 'Use Airplane profile'
        capture_window(root, output / 'flaps-profile-guidance.png')
        checks.append('General profile explains disabled flaps bindings and offers a matching profile')
        app.profile_hint_button.invoke()
        root.update()
        assert app.profile.category == 'AIRPLANE'
        assert app.profile.name == 'Commercial Airbus Flaps'
        assert app.profile.device.attrib == identity
        assert app.profile.device.find('Axes/Axis').get('AxisDeadZone') == '9'
        assert app.selected == ('AIRCRAFT', 'KEY_AXIS_FLAPS_SET')
        get_input = next(button for slot, label, button in app.binding_buttons if slot == 'Primary' and label == 'Get Input')
        assert not get_input.instate(['disabled'])
        checks.append('One-click type switch keeps name, controller, tuning and flaps selection')
        app.undo()
        assert app.profile.category == 'GENERAL' and get_input.instate(['disabled'])
        app.redo()
        assert app.profile.category == 'AIRPLANE' and not get_input.instate(['disabled'])
        checks.append('Profile type switch supports Undo and Redo')
        baseline = {obj.offset: 0.0 if obj.kind == 'axis' else False if obj.kind == 'button' else -1 for obj in reader.objects}
        axis = next(obj for obj in reader.objects if obj.kind == 'axis')
        with patch.object(reader, 'read', return_value=baseline), patch('msfs_config.app.time.monotonic', return_value=100):
            get_input.invoke()
        moved = dict(baseline)
        moved[axis.offset] = .85
        for now in (100.1, 100.9, 101.1):
            with patch.object(reader, 'read', return_value=moved), patch('msfs_config.app.time.monotonic', return_value=now):
                app.poll()
        assert app.profile.keys(*app.selected, 'Primary')
        assert int(app.profile.action(*app.selected).get('Flag')) & 4
        assert Profile.from_text(app.profile.to_text()).category == 'AIRPLANE'
        capture_window(root, output / 'flaps-axis-bound.png')
        checks.append('Flaps axis captures a verified Windows axis and exports the correct profile category')
        original = app.profile.to_text()
        app.type_var.set('Helicopter controls')
        app.category_changed()
        root.update()
        dialog = next(child for child in root.winfo_children() if isinstance(child, tk.Toplevel))
        assert app.profile.to_text() == original
        assert app.type_var.get() == 'Airplane controls'
        assert any(isinstance(widget, ttk.Combobox) and widget.get() == 'Helicopter controls' for widget in widgets(dialog))
        dialog.destroy()
        checks.append('Changing an existing profile opens a separate matching profile dialog; cancel preserves it')

        # Delay a real read-only Store scan to verify window responsiveness during I/O.
        release_scan = threading.Event()
        beats = []
        def delayed_scan(cancel_event=None):
            release_scan.wait(2)
            return scan_profiles(cancel_event=cancel_event)
        with patch('msfs_config.local_profiles.scan_profiles', side_effect=delayed_scan):
            saved = next(widget for widget in widgets(root) if isinstance(widget, ttk.Button) and widget.cget('text') == 'Saved')
            start = time.perf_counter()
            saved.invoke()
            opening_seconds = time.perf_counter() - start
            assert opening_seconds < .3, opening_seconds
            window = app.saved_browser_window
            root.after(30, lambda: beats.append(time.monotonic()))
            pump_until(lambda: bool(beats))
            assert app.profile_scan_running
            assert 'Loading saved profiles' in app.profile_scan_progress.get()
            capture_window(window, output / 'saved-profiles-loading.png')
            window.destroy()
            assert app.saved_profile_browser().winfo_exists()
            release_scan.set()
            pump_until(lambda: not app.profile_scan_running, 20)
        assert app.controller is reader, 'Background discovery must not reopen the active controller.'
        checks.append('Saved opens immediately with loading feedback; window remains responsive and can close/reopen during scan')
        window = app.saved_browser_window
        listing = next(widget for widget in widgets(window) if isinstance(widget, ttk.Treeview))
        assert len(listing.get_children()) == len(app.saved_profiles)
        for row in app.saved_profiles:
            assert row['bindings'] == row['profile'].bound_slot_count()
        with patch.object(Profile, 'keys', side_effect=AssertionError('Repeated key lookup')):
            app.saved_browser_refresh()
        assert app.saved_profile_browser() is window
        checks.append('Saved counts use cached single-pass data and repeated Saved clicks reuse the browser')
        with patch('msfs_config.local_profiles.scan_profiles', side_effect=OSError('Test read failure')):
            app.scan_saved_profiles(quiet=True)
            pump_until(lambda: not app.profile_scan_running)
        assert 'Try Refresh' in app.profile_scan_progress.get()
        assert len(listing.get_children()) == len(app.saved_profiles)
        checks.append('Read failures show a retry message and retain the last available profiles')
        with patch.object(app.catalogue, 'learn', side_effect=ValueError('Test reference failure')):
            app.scan_saved_profiles(quiet=True)
            pump_until(lambda: not app.profile_scan_running, 20)
        assert 'could not learn' in app.profile_scan_progress.get()
        checks.append('Reference-learning errors end the loading state and preserve browser access')
        app.find_input()
        capture = app.capture
        app.scan_saved_profiles(quiet=True)
        pump_until(lambda: not app.profile_scan_running, 20)
        assert 'Could not' not in app.profile_scan_progress.get()
        assert app.controller is reader and app.capture is capture
        checks.append('Refresh successfully recovers after a failed scan')
        checks.append('Background reference discovery preserves active Find input and its controller reader')
        app.cancel_capture()
        if app.saved_profiles:
            largest = max(app.saved_profiles, key=lambda row: len(row['profile'].actions()))
            index = str(app.saved_profiles.index(largest))
            listing.selection_set(index)
            expected = largest['profile'].to_text()
            opener = next(widget for widget in widgets(window) if isinstance(widget, ttk.Button) and widget.cget('text') == 'Open selected copy')
            start = time.perf_counter()
            def refresh_during_prompt():
                app.saved_profiles.reverse()
                app.saved_browser_refresh()
                return True
            with patch.object(app, 'can_discard', side_effect=refresh_during_prompt):
                opener.invoke()
            assert app.profile.to_text() == expected and app.profile is not largest['profile']
            assert time.perf_counter() - start < 2
            checks.append('The largest real Store profile opens promptly as a separate lossless copy')
            checks.append('A refresh during the export prompt preserves the originally chosen saved profile')
        started, finished = threading.Event(), threading.Event()
        def cancellable_scan(cancel_event=None):
            started.set()
            cancel_event.wait(2)
            assert cancel_event.is_set()
            finished.set()
            return []
        with patch('msfs_config.local_profiles.scan_profiles', side_effect=cancellable_scan):
            app.scan_saved_profiles(quiet=True)
            pump_until(started.is_set)
            app.saved_text = app.profile.to_text()
            app.close()
            assert finished.wait(1)
        checks.append('Closing during a background scan cancels work without callbacks into a destroyed window')
        assert not errors, errors
        result = {'passed': len(checks), 'checks': checks, 'saved_window_open_seconds': round(opening_seconds, 4),
                  'local_profiles_read': len(app.saved_profiles), 'callback_errors': errors,
                  'input_stream': 'simulated axis movement; real Windows controller enumeration'}
        (output / 'saved-workflow-qa.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.saved_text = app.profile.to_text() if app.profile else None
        try:
            if root.winfo_exists():
                app.close()
        except tk.TclError:
            pass


if __name__ == '__main__':
    main()
