import ctypes
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from msfs_config.catalogue import Catalogue
from msfs_config.labels import ControllerLabels
from msfs_config.local_profiles import scan_profiles, is_managed_save
from msfs_config.profiles import Profile, AXIS_DEFAULTS
from msfs_config.system_inputs import SystemDevice, XInputController, XInputState


def reference(name, keys):
    profile = Profile.new('Reference', {'DeviceName': name, 'GUID': '{0}',
                         'ProductID': '1', 'CompositeID': '0', 'HWVer': '1.0.0.0'})
    profile.set_binding('TEST', 'TEST_ACTION', 'Primary', keys)
    return profile


class SystemInputTests(unittest.TestCase):
    def test_keyboard_and_gamepad_names_resolve_in_their_own_family(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Path(folder) / 'library.json'
            catalogue = Catalogue(storage=store)
            catalogue.learn(reference('Keyboard', [('A', 65), ('.', 190), ('-', 189)]))
            catalogue.learn(reference('XInput Gamepad', [('A', 0)]))
            catalogue.save_library()
            restored = Catalogue(storage=store)
        self.assertEqual(restored.resolve('A', 'keyboard'), ('A', 65))
        self.assertEqual(restored.resolve('A', 'gamepad'), ('A', 0))
        self.assertEqual(restored.resolve('.', 'keyboard'), ('.', 190))
        self.assertEqual(restored.resolve('-', 'keyboard'), ('-', 189))

    def test_conflicting_id_is_quarantined_only_in_affected_family(self):
        catalogue = Catalogue()
        catalogue.learn(reference('Keyboard', [('A', 65)]))
        catalogue.learn(reference('Keyboard', [('A', 66)]))
        catalogue.learn(reference('XInput', [('A', 0)]))
        self.assertIsNone(catalogue.resolve('A', 'keyboard'))
        self.assertEqual(catalogue.resolve('A', 'gamepad'), ('A', 0))

    def test_old_joystick_library_migrates_and_keeps_conflict_quarantine(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'old.json'
            path.write_text(json.dumps({'keys': {'Joystick Button 99': 98}, 'actions': [],
                                        'conflicts': ['joystickbutton1']}), encoding='utf-8')
            catalogue = Catalogue(storage=path)
            self.assertEqual(catalogue.resolve('Joystick Button 99', 'joystick'), ('Joystick Button 99', 98))
            self.assertIsNone(catalogue.resolve('Joystick Button 1', 'joystick'))

    def test_saved_reference_cannot_silently_replace_a_bundled_id(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.json'
            path.write_text(json.dumps({'scoped_keys': {'joystick': {'Joystick Button 1': 99}}}), encoding='utf-8')
            catalogue = Catalogue(storage=path)
            self.assertIsNone(catalogue.resolve('Joystick Button 1', 'joystick'))

    def test_builtin_device_sentinel_is_valid_only_for_native_builtin_profiles(self):
        for name in ('Keyboard', 'Mouse', 'XInput'):
            self.assertFalse(reference(name, [('A', 0)]).validate())
        self.assertTrue(reference('Joystick', [('A', 0)]).validate())
        profile = reference('Keyboard', [('A', 65)])
        profile.format = 'sdk'
        # SDK documents still require their documented UUID identity.
        profile.root.tag = 'DefaultInput'
        from xml.etree.ElementTree import Element
        wrapper = Element('ProfileDocument')
        wrapper.append(profile.root)
        profile.root = wrapper
        self.assertTrue(profile.validate())

    def test_aliases_keep_keyboard_punctuation_and_builtin_families_separate(self):
        labels = ControllerLabels(storage=False)
        labels.set('{0}:keyboard', '.', 'Period')
        labels.set('{0}:keyboard', '-', 'Minus')
        labels.set('{0}:keyboard', 'A', 'Letter A')
        labels.set('{0}:gamepad', 'A', 'Confirm')
        self.assertEqual(labels.get('{0}:keyboard', '.'), 'Period')
        self.assertEqual(labels.get('{0}:keyboard', '-'), 'Minus')
        self.assertEqual(labels.get('{0}:keyboard', 'A'), 'Letter A')
        self.assertEqual(labels.get('{0}:gamepad', 'A'), 'Confirm')

    def test_numbered_imported_axes_remain_editable_without_assuming_directinput_mapping(self):
        profile = reference('GInput Joystick', [('JOYSTICK L-Axis 1', 65538)])
        from xml.etree.ElementTree import SubElement
        parent = SubElement(profile.device, 'Axes')
        for index in range(16):
            SubElement(parent, 'Axis', AxisName=str(index), **AXIS_DEFAULTS)
        self.assertEqual(profile.axis_names(), tuple(str(index) for index in range(16)))
        profile.set_axis('15', {'AxisDeadZone': '12'})
        self.assertEqual(profile.device.find('Axes/Axis[@AxisName="15"]').get('AxisDeadZone'), '12')
        with self.assertRaises(ValueError):
            profile.set_axis('X', {'AxisDeadZone': '12'})
        self.assertEqual(Profile.from_text(profile.to_text()).axis_names(), profile.axis_names())

    def test_saved_profile_scan_is_read_only_and_ignores_unrelated_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            managed = Path(folder) / 'wgs'
            target = managed / 'account' / 'container' / 'profile'
            target.parent.mkdir(parents=True)
            reference('Keyboard', [('A', 65)]).save(target)
            before = target.read_bytes()
            (target.parent / 'other').write_bytes(b'Unrelated binary data' * 10)
            rows = scan_profiles([managed])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['path'], target)
            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(is_managed_save(target, [managed]))
            self.assertFalse(is_managed_save(Path(folder) / 'export.xml', [managed]))

    def test_xinput_translation_reads_buttons_triggers_sticks_and_directional_inputs(self):
        class FakeAPI:
            disconnected = False
            def XInputGetState(self, slot, pointer):
                state = ctypes.cast(pointer, ctypes.POINTER(XInputState)).contents
                state.pad.buttons = 0x1000 | 0x0200 | 0x0004
                state.pad.lt, state.pad.rt = 255, 0
                state.pad.lx, state.pad.ly, state.pad.rx, state.pad.ry = -32768, 32767, 0, -16384
                return 1167 if self.disconnected else 0
        api = FakeAPI()
        device = SystemDevice('Pad', {'GUID': '{0}', 'DeviceName': 'XInput', 'ProductID': '1'}, 'gamepad', {})
        with patch('msfs_config.system_inputs.xinput_api', return_value=api):
            controller = XInputController(device)
        values = controller.read()
        by_name = {obj.information: values[obj.offset] for obj in controller.objects}
        self.assertTrue(by_name['A'] and by_name['RB'] and by_name['D-PAD Left'])
        self.assertFalse(by_name['B'])
        self.assertEqual(by_name['LS X'], -1)
        self.assertEqual(by_name['LS Y'], 1)
        self.assertEqual(by_name['LT'], 1)
        self.assertEqual(by_name['RT'], 0)
        self.assertTrue(by_name['LS Left'] and by_name['LS Up'] and by_name['RS Down'])
        self.assertFalse(by_name['RS Up'])
        axis = next(obj for obj in controller.objects if obj.information == 'LS X')
        self.assertEqual(axis.msfs_name('-'), 'LS Left')
        api.disconnected = True
        with self.assertRaises(OSError):
            controller.read()


if __name__ == '__main__':
    unittest.main()
