import json
from pathlib import Path
import tempfile
import unittest
import uuid
import xml.etree.ElementTree as ET

from msfs_config.profiles import Profile, semantic_signature
from msfs_config.setups import ControllerSetup, SetupStore


DEVICE = {'DeviceName': 'Test joystick', 'GUID': '{12345678-1234-1234-1234-123456789abc}',
          'ProductID': '42', 'CompositeID': '0', 'HWVer': '1.0.0.0'}


class SetupTests(unittest.TestCase):
    def setup(self):
        airplane = Profile.new('Commercial Airbus', DEVICE, 'AIRPLANE', ['X'])
        airplane.set_binding('AIRCRAFT', 'KEY_AXIS_FLAPS_SET', 'Primary', [('Joystick L-Axis X', 256)], {'Flag': '4'})
        airplane.set_axis('X', {'AxisDeadZone': '9'})
        setup = ControllerSetup(airplane)
        general = setup.ensure_category('GENERAL')
        general.profile.set_binding('MODES', 'KEY_COCKPIT_RESET', 'Primary', [('Joystick Button 1', 0)])
        return setup

    def test_category_creation_keeps_flight_and_camera_independent_and_copies_axis_tuning(self):
        setup = self.setup()
        self.assertEqual(setup.active.profile.category, 'AIRPLANE')
        self.assertEqual(setup.active.profile.bound_slot_count(), 1)
        general = setup.category('GENERAL')
        self.assertEqual(general.profile.device.find('Axes/Axis').get('AxisDeadZone'), '9')
        self.assertNotIn(('AIRCRAFT', 'KEY_AXIS_FLAPS_SET'), general.profile.actions())
        self.assertNotIn(('MODES', 'KEY_COCKPIT_RESET'), setup.active.profile.actions())
        self.assertIs(setup.ensure_category('GENERAL'), general)
        self.assertEqual(len(setup.layers), 2)

    def test_all_layers_active_selection_names_and_aliases_survive_save_reopen(self):
        setup = self.setup()
        setup.active_id = setup.category('GENERAL').id
        ET.SubElement(setup.active.profile.device, 'FutureMetadata', Value='keep')
        setup.active.profile.device.append(ET.Comment('Unknown comment'))
        before = [semantic_signature(layer.profile.root) for layer in setup.layers]
        labels = {DEVICE['GUID'].lower(): {'Joystick Button 1': 'Reset camera'}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Controller.msfssetup'
            setup.save(path, labels)
            reopened, names = ControllerSetup.load(path)
        self.assertEqual(names, labels)
        self.assertEqual(reopened.id, setup.id)
        self.assertEqual(reopened.active_id, setup.active_id)
        self.assertEqual([semantic_signature(layer.profile.root) for layer in reopened.layers], before)

    def test_another_controller_or_same_guid_different_input_family_is_rejected(self):
        setup = self.setup()
        other = dict(DEVICE, GUID='{aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa}')
        with self.assertRaises(ValueError):
            setup.add(Profile.new('Other', other))
        keyboard = Profile.new('Keys', {'DeviceName': 'Keyboard', 'GUID': '{0}', 'CompositeID': '0'})
        builtin = ControllerSetup(keyboard)
        with self.assertRaises(ValueError):
            builtin.add(Profile.new('Mouse', {'DeviceName': 'Mouse', 'GUID': '{0}', 'CompositeID': '0'}))

    def test_alternative_presets_are_added_without_replacing_existing_bindings(self):
        setup = self.setup()
        original = setup.active.profile.to_text()
        added = setup.add(Profile.new('Another airplane', DEVICE, 'AIRPLANE'))
        self.assertEqual(len(setup.layers), 3)
        self.assertEqual(setup.layers[0].profile.to_text(), original)
        self.assertIs(setup.category('AIRPLANE'), added)

    def test_aircraft_specific_layer_is_kept_separate_from_category_layer(self):
        setup = self.setup()
        specific = Profile.new('Specific plane', DEVICE, 'AIRPLANE')
        specific.device.find('AircraftInfo').set('AircraftName', 'Example A320')
        layer = setup.add(specific)
        generic = setup.ensure_category('AIRPLANE')
        self.assertIsNot(generic, layer)
        self.assertEqual(layer.profile.device.find('AircraftInfo').get('AircraftName'), 'Example A320')

    def test_corrupt_setup_does_not_hide_other_local_working_copies(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SetupStore(folder)
            setup = self.setup()
            store.save(setup)
            (Path(folder) / 'corrupt.msfssetup').write_text('{not JSON', encoding='utf-8')
            (Path(folder) / 'xml-corrupt.msfssetup').write_text(json.dumps({'schema': 1, 'id': str(uuid.uuid4()),
                'name': 'broken', 'active': '', 'layers': [{'id': str(uuid.uuid4()), 'profile_xml': '<bad'}]}), encoding='utf-8')
            rows = store.entries()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['setup'].id, setup.id)
            self.assertEqual(len(rows[0]['setup'].layers), 2)

    def test_duplicate_ids_and_missing_active_layer_are_rejected(self):
        setup = self.setup()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.msfssetup'
            data = setup.to_dict()
            data['layers'][1]['id'] = data['layers'][0]['id']
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                ControllerSetup.load(path)
            data = setup.to_dict()
            data['active'] = str(uuid.uuid4())
            path.write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaises(ValueError):
                ControllerSetup.load(path)

    def test_export_splits_valid_native_files_and_writes_import_instructions(self):
        setup = self.setup()
        with tempfile.TemporaryDirectory() as folder:
            files, guide = setup.export(folder)
            self.assertEqual(len(files), 2)
            exported = {Profile.load(path).category: Profile.load(path) for path in files}
            self.assertEqual(exported['AIRPLANE'].bound_slot_count(), 1)
            self.assertEqual(exported['GENERAL'].bound_slot_count(), 1)
            self.assertIn('one preset for each profile type', guide.read_text(encoding='utf-8'))
            self.assertTrue(all('<ProfileDocument>' not in path.read_text(encoding='utf-8') for path in files))

    def test_export_never_overwrites_existing_files_or_colliding_layer_names(self):
        setup = self.setup()
        setup.add(Profile.from_text(setup.layers[0].profile.to_text()))
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / 'Commercial Airbus - Airplane.xml'
            existing.write_text('keep', encoding='utf-8')
            files, guide = setup.export(folder)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'keep')
            self.assertEqual(len(set(files)), 3)
            again, new_guide = setup.export(folder)
            self.assertFalse(set(files).intersection(again))
            self.assertNotEqual(guide, new_guide)

    def test_invalid_layer_is_rejected_before_any_export_files_are_written(self):
        setup = self.setup()
        setup.category('GENERAL').profile.action('MODES', 'KEY_COCKPIT_RESET').set('Flag', 'bad')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                setup.export(folder)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_sdk_sources_are_not_mislabeled_as_native_setup_exports(self):
        profile = Profile.from_text('<DefaultInput><Device DeviceName="Test joystick" GUID="{12345678-1234-1234-1234-123456789abc}" ProductID="42" CompositeID="0" HWVer="1"/></DefaultInput>')
        setup = ControllerSetup(profile)
        with self.assertRaises(ValueError):
            setup.ensure_category('AIRPLANE')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                setup.export(folder)
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
