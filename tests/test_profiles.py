import tempfile
import unittest
from pathlib import Path

from msfs_config.catalogue import Catalogue
from msfs_config.devices import InputObject, GUID, changed_inputs
from msfs_config.profiles import Profile, semantic_signature, validate_axis
from msfs_config.labels import ControllerLabels

IDENTITY = {'DeviceName': 'Test controller', 'GUID': '{12345678-1234-1234-1234-123456789abc}',
            'ProductID': '42', 'CompositeID': '0', 'HWVer': '1.0.0.0'}


class ProfileTests(unittest.TestCase):
    def test_every_real_export_round_trips_without_data_loss(self):
        files = list(Path('research/community-profiles/profiles').glob('*.xml'))
        self.assertEqual(len(files), 48, 'Download the public reference repository before running this corpus test.')
        with tempfile.TemporaryDirectory() as tmp:
            for index, path in enumerate(files):
                with self.subTest(path=path.name):
                    original = Profile.load(path)
                    target = Path(tmp) / f'{index}.xml'
                    original.save(target)
                    reopened = Profile.load(target)
                    self.assertEqual(semantic_signature(original.root), semantic_signature(reopened.root))
                    self.assertEqual(original.format, 'native')
                    self.assertNotIn('<ProfileDocument>', target.read_text(encoding='utf-8'))

    def test_binding_edit_keeps_secondary_unknown_data_chords_and_axes(self):
        profile = Profile.from_text('''<Version Num="-1"/><FriendlyName Locked="false">Example</FriendlyName>
            <Device DeviceName="Test" GUID="{12345678-1234-1234-1234-123456789abc}" ProductID="42" CompositeID="0" HWVer="1">
            <CustomFutureField Value="preserve"/><Context ContextName="BASIC_CONTROL"><Action ActionName="KEY_GEAR_TOGGLE" Flag="8194" Custom="keep">
            <Primary><KEY Information="Joystick Button 1">0</KEY><Axis AxisName="X" AxisDeadZone="7"/></Primary>
            <Secondary><KEY Information="Joystick Button 2">1</KEY></Secondary><FutureOption Name="untouched"/>
            </Action></Context></Device>''')
        before_secondary = semantic_signature(profile.action('BASIC_CONTROL', 'KEY_GEAR_TOGGLE').find('Secondary'))
        profile.set_binding('BASIC_CONTROL', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 3', 2), ('Joystick Button 4', 3)])
        reopened = Profile.from_text(profile.to_text())
        action = reopened.action('BASIC_CONTROL', 'KEY_GEAR_TOGGLE')
        self.assertEqual(before_secondary, semantic_signature(action.find('Secondary')))
        self.assertEqual(action.get('Custom'), 'keep')
        self.assertEqual(action.find('Primary/Axis').get('AxisDeadZone'), '7')
        self.assertIsNotNone(reopened.device.find('CustomFutureField'))
        self.assertIsNotNone(action.find('FutureOption'))
        self.assertEqual(len(reopened.keys('BASIC_CONTROL', 'KEY_GEAR_TOGGLE', 'Primary')), 2)

    def test_sdk_format_is_preserved_separately_from_native_import(self):
        profile = Profile.from_text('<DefaultInput Primary="1" PlatformAvailability="PC"><Version Num="2"/><Device DeviceName="Test" GUID="{12345678-1234-1234-1234-123456789abc}" ProductID="0x42" CompositeID="0" HWVer="1"><Axes/></Device></DefaultInput>')
        profile.set_binding('AIRCRAFT', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 1', 0)])
        self.assertEqual(profile.format, 'sdk')
        profile.name = 'Keep SDK schema unchanged'
        self.assertIsNone(profile.container.find('FriendlyName'))
        restored = Profile.from_text(profile.to_text())
        self.assertEqual(semantic_signature(profile.root), semantic_signature(restored.root))

    def test_unresolved_inputs_cannot_be_exported(self):
        profile = Profile.new('Test', IDENTITY)
        action = profile.action('BASIC_CONTROL', 'KEY_GEAR_TOGGLE', True)
        import xml.etree.ElementTree as ET
        key = ET.SubElement(ET.SubElement(action, 'Primary'), 'KEY', Information='Unknown')
        key.text = 'pending'
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'bad.xml'
            with self.assertRaises(ValueError):
                profile.save(target)
            self.assertFalse(target.exists())

    def test_key_zero_is_valid_and_missing_button_ids_are_not_extrapolated(self):
        cat = Catalogue()
        self.assertEqual(cat.resolve('Joystick Button 1'), ('Joystick Button 1', 0))
        self.assertIsNone(cat.resolve('Joystick Button 17'))
        self.assertEqual(cat.resolve('Joystick L-Axis X')[1], 1026)
        self.assertEqual(cat.resolve('Joystick Pov Left')[1], 259)

    def test_conflicting_learned_id_is_quarantined(self):
        cat = Catalogue()
        profile = Profile.new('Test', IDENTITY)
        profile.set_binding('AIRCRAFT', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 1', 991)])
        cat.learn(profile)
        self.assertIsNone(cat.resolve('Joystick Button 1'))

    def test_learning_and_conflict_quarantine_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / 'library.json'
            cat = Catalogue(storage=storage)
            profile = Profile.new('Test', IDENTITY)
            profile.set_binding('AIRCRAFT', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 17', 16)])
            cat.learn(profile)
            cat.save_library()
            restarted = Catalogue(storage=storage)
            self.assertEqual(restarted.resolve('Joystick Button 17'), ('Joystick Button 17', 16))
            profile.set_binding('AIRCRAFT', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 17', 900)])
            restarted.learn(profile)
            restarted.save_library()
            self.assertIsNone(Catalogue(storage=storage).resolve('Joystick Button 17'))

    def test_axis_parameters_use_ranges_seen_in_real_exports(self):
        validate_axis({'AxisSensitivy': '-70', 'AxisSensitivyMinus': '50', 'AxisResponseRate': '-1'})
        for values in [{'AxisDeadZone': '101'}, {'AxisResponseRate': '50'}, {'AxisNeutral': '-101'}]:
            with self.assertRaises(ValueError):
                validate_axis(values)

    def test_native_profile_category_and_guid_are_written(self):
        profile = Profile.new('My airplane', IDENTITY, 'AIRPLANE', ['X', 'rZ'])
        restored = Profile.from_text(profile.to_text())
        self.assertEqual(restored.category, 'AIRPLANE')
        self.assertEqual(restored.device.get('GUID'), IDENTITY['GUID'])
        self.assertEqual(restored.name, 'My airplane')
        self.assertEqual(restored.validate(), [])

    def test_dtd_and_entity_definitions_are_rejected(self):
        with self.assertRaises(ValueError):
            Profile.from_text('<!DOCTYPE Device [<!ENTITY x "hello">]><Device/>')


class CaptureTests(unittest.TestCase):
    def setUp(self):
        guid = GUID.from_string('12345678-1234-1234-1234-123456789abc')
        self.axis = InputObject('axis', 0, 'X axis', 0, 2, guid, 'X')
        self.button = InputObject('button', 0, 'Button 0', 48, 12, guid)
        self.pov = InputObject('pov', 0, 'Hat', 32, 16, guid)

    def test_noise_is_ignored_and_button_zero_is_detected(self):
        objects = [self.axis, self.button]
        self.assertEqual(changed_inputs(objects, {0: 0.0, 48: False}, {0: .02, 48: False}), [])
        self.assertEqual(changed_inputs(objects, {0: 0.0, 48: False}, {0: .02, 48: True}), ['Joystick Button 1'])

    def test_split_axis_and_hat_diagonals(self):
        self.assertEqual(changed_inputs([self.axis], {0: .2}, {0: -.4}, True), ['Joystick L-Axis X-'])
        self.assertEqual(changed_inputs([self.pov], {32: -1}, {32: 4500}), ['Joystick Pov Up_Right'])
        self.assertEqual(changed_inputs([self.pov], {32: 4500}, {32: -1}), [])


class LabelTests(unittest.TestCase):
    def test_names_persist_without_changing_binding_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp) / 'labels.json'
            labels = ControllerLabels(storage)
            labels.set(IDENTITY['GUID'], 'Joystick Button 1', 'Landing gear')
            labels.set(IDENTITY['GUID'], 'Joystick L-Axis X ', 'Roll')
            restarted = ControllerLabels(storage)
            self.assertEqual(restarted.get(IDENTITY['GUID'].upper(), 'Joystick Button 1'), 'Landing gear')
            self.assertEqual(restarted.get(IDENTITY['GUID'], 'Joystick L-Axis X+'), 'Roll +')
            profile = Profile.new('Example', IDENTITY)
            profile.set_binding('SURFACES', 'KEY_GEAR_TOGGLE', 'Primary', [('Joystick Button 1', 0)])
            self.assertNotIn('Landing gear', profile.to_text())
            self.assertEqual(Profile.from_text(profile.to_text()).keys('SURFACES', 'KEY_GEAR_TOGGLE', 'Primary'), [('Joystick Button 1', '0')])
            restarted.set(IDENTITY['GUID'], 'Joystick Button 1', '')
            self.assertEqual(ControllerLabels(storage).get(IDENTITY['GUID'], 'Joystick Button 1'), '')

    def test_labels_are_specific_to_each_controller(self):
        labels = ControllerLabels(False)
        labels.set('first-guid', 'Joystick Button 17', 'Flaps')
        labels.set('second-guid', 'Joystick Button 17', 'Lights')
        self.assertEqual(labels.get('first-guid', 'Joystick Button 17'), 'Flaps')
        self.assertEqual(labels.get('second-guid', 'Joystick Button 17'), 'Lights')
        self.assertIsNone(Catalogue().resolve('Joystick Button 17'))


if __name__ == '__main__':
    unittest.main()
