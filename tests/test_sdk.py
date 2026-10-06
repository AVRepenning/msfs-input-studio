import tempfile
import unittest
from pathlib import Path

from msfs_config.catalogue import Catalogue
from msfs_config.conflicts import binding_conflicts
from msfs_config.sdk import SDKDocument
from msfs_config.profiles import Profile, semantic_signature

IDENTITY = {'DeviceName': 'Test', 'GUID': '{12345678-1234-1234-1234-123456789abc}',
            'ProductID': '42', 'CompositeID': '0', 'HWVer': '1'}


class SDKTests(unittest.TestCase):
    def test_gamepad_device_config_uses_scoped_references_and_deduplicates_directions(self):
        from msfs_config.system_inputs import SystemDevice, SystemObject
        from msfs_config.labels import ControllerLabels
        profile = Profile.new('Pad reference', dict(IDENTITY, DeviceName='XInput', GUID='{0}'))
        profile.set_binding('TEST', 'TEST', 'Primary', [('LT', 11), ('LS X', 12), ('LS Left', 13), ('LS Right', 14)])
        catalogue = Catalogue()
        catalogue.learn(profile)
        device = SystemDevice('Pad', profile.device.attrib, 'gamepad', {})
        device.objects = [SystemObject('LT', 'LT', 1, kind='axis', axis='Z', family='gamepad'),
                          SystemObject('LS X', 'LS X', 2, kind='axis', axis='X', family='gamepad'),
                          SystemObject('LS Right', 'LS Right', 3, family='gamepad', derived=True)]
        labels = ControllerLabels(storage=False)
        labels.set('{0}:gamepad', 'LS Right', 'Look right')
        document = SDKDocument.device_config(device, labels, catalogue)
        names = [node.get('buttonId') for node in document.root.findall('Device/ButtonTT')]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), {'LT', 'LS X', 'LS Left', 'LS Right'})
        self.assertEqual(document.root.find('Device/ButtonTT[@buttonId="LS Right"]').get('TT'), 'Look right')

    def test_device_config_round_trip_preserves_extensions_and_icon_ampersands(self):
        document = SDKDocument.from_text('''<DeviceConfig Custom="keep"><!--keep comment-->
          <Device ProductID="0x1234" DisplayName="Flight controller" TextureFolder="controller" Priority="-1" Future="keep">
            <ButtonTT buttonId="Joystick Button 1" TT="Landing gear"/>
            <MergeIcons SourceIcons="A&amp;B" TargetIcon="stick" TargetTT="Stick"/>
            <Future Extension="yes"/>
          </Device></DeviceConfig>''')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'DeviceConfig.xml'
            document.save(path)
            restored = SDKDocument.load(path)
        self.assertEqual(semantic_signature(document.root), semantic_signature(restored.root))
        self.assertEqual(restored.root.find('Device/MergeIcons').get('SourceIcons'), 'A&B')

    def test_device_config_rejects_missing_required_fields_and_invalid_product_id(self):
        document = SDKDocument.from_text('<DeviceConfig><Device ProductID="42" Priority="bad"/></DeviceConfig>')
        self.assertGreaterEqual(len(document.validate()), 4)

    def test_actiondb_import_keeps_types_categories_english_metadata_and_existing_defaults(self):
        document = SDKDocument.from_text('''<ActionDefinition><Actions><Action>
            <Name>MY_TEST_INPUT</Name><Context>INPUT_EVENTS</Context><Type>AXIS</Type>
            <TT_Name>Collective lever</TT_Name><TT_Function>Lift the helicopter</TT_Function>
            <TT_Category_Main>Flight controls</TT_Category_Main><TT_Category_Sub>Helicopter</TT_Category_Sub>
            </Action></Actions></ActionDefinition>''')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'learned.json'
            catalogue = Catalogue(storage=path)
            original = dict(catalogue.actions[('AIRCRAFT', 'KEY_GEAR_TOGGLE')]['attributes'])
            self.assertEqual(catalogue.learn_actiondb(document, 'HELICOPTER'), 1)
            catalogue.save_library()
            restored = Catalogue(storage=path)
        entry = restored.actions[('INPUT_EVENTS', 'MY_TEST_INPUT')]
        self.assertEqual(entry['attributes']['Flag'], '4')
        self.assertEqual(entry['categories'], ['HELICOPTER'])
        self.assertEqual(entry['display_name'], 'Collective lever')
        self.assertEqual(entry['description'], 'Lift the helicopter')
        self.assertEqual(restored.actions[('AIRCRAFT', 'KEY_GEAR_TOGGLE')]['attributes'], original)

    def test_invalid_actiondb_does_not_partially_modify_library(self):
        catalogue = Catalogue()
        before = len(catalogue.actions)
        document = SDKDocument.from_text('<ActionDefinition><Actions><Action><Name>INVALID ACTION</Name></Action></Actions></ActionDefinition>')
        with self.assertRaises(ValueError):
            catalogue.learn_actiondb(document, 'AIRPLANE')
        self.assertEqual(len(catalogue.actions), before)

    def test_localization_tokens_do_not_replace_readable_names(self):
        document = SDKDocument.from_text('''<ActionDefinition><Actions><Action><Name>MY_SWITCH</Name>
            <Context>INPUT_EVENTS</Context><Type>DIGITAL</Type><TT_Name>TT:MY.SWITCH</TT_Name>
            <TT_Category_Main/><TT_Category_Sub/></Action></Actions></ActionDefinition>''')
        catalogue = Catalogue()
        catalogue.learn_actiondb(document, 'AIRPLANE')
        self.assertNotIn('display_name', catalogue.actions[('INPUT_EVENTS', 'MY_SWITCH')])

    def test_remap_and_or_alternatives_round_trip(self):
        document = SDKDocument.from_text('''<RemapActions><RemapAction str="STR_FLAPS_DOWN" player="ALL">
            <InputAction><Input>A</Input><Input>B</Input></InputAction>
            <InputAction><Input>C</Input></InputAction></RemapAction></RemapActions>''')
        self.assertFalse(document.validate())
        restored = SDKDocument.from_text(document.to_text())
        self.assertEqual(semantic_signature(document.root), semantic_signature(restored.root))
        self.assertEqual(len(restored.root.findall('.//InputAction')), 2)

    def test_incomplete_remap_is_blocked(self):
        document = SDKDocument.from_text('<RemapActions><RemapAction str="wrong" player="PLAYER1"><InputAction/></RemapAction></RemapActions>')
        self.assertEqual(len(document.validate()), 2)

    def test_sdk_entities_and_unexpected_roots_are_rejected(self):
        for text in ('<!DOCTYPE x><DeviceConfig/>', '<Other/>'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                SDKDocument.from_text(text)

    def test_conflicts_cover_complete_and_subset_chords_without_cross_context_false_positives(self):
        profile = Profile.new('Test', IDENTITY)
        profile.set_binding('FLIGHT', 'A', 'Primary', [('Button 1', 0)])
        profile.set_binding('FLIGHT', 'B', 'Secondary', [('Button 1', 0), ('Button 2', 1)])
        profile.set_binding('CAMERA', 'C', 'Primary', [('Button 1', 0)])
        profile.set_binding('FLIGHT', 'D', 'Primary', [('Button 1', 0)])
        conflicts = binding_conflicts(profile)
        self.assertEqual(set(conflicts), {('FLIGHT', 'A'), ('FLIGHT', 'B'), ('FLIGHT', 'D')})
        self.assertTrue(any(item[3] == 'Same input / chord' for item in conflicts[('FLIGHT', 'A')]))
        self.assertTrue(any(item[3] == 'Button also used inside a chord' for item in conflicts[('FLIGHT', 'A')]))

    def test_both_slots_on_one_action_are_not_reported_as_conflicts(self):
        profile = Profile.new('Test', IDENTITY)
        for slot in ('Primary', 'Secondary'):
            profile.set_binding('FLIGHT', 'A', slot, [('Button 1', 0)])
        self.assertFalse(binding_conflicts(profile))


if __name__ == '__main__':
    unittest.main()
