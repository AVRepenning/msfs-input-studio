import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

from msfs_config.conflicts import binding_conflicts
from msfs_config.local_profiles import scan_profiles
from msfs_config.profiles import Profile, semantic_signature


def large_profile(count=2200):
    profile = Profile.new('Large saved profile', {'DeviceName': 'Test',
        'GUID': '{12345678-1234-1234-1234-123456789abc}', 'ProductID': '42', 'CompositeID': '0', 'HWVer': '1'})
    context = ET.SubElement(profile.device, 'Context', ContextName='AIRCRAFT')
    for index in range(count):
        action = ET.SubElement(context, 'Action', ActionName=f'KEY_TEST_{index}', Flag='2')
        primary = ET.SubElement(action, 'Primary')
        ET.SubElement(primary, 'KEY', Information=f'Button {index}').text = str(index)
        if index % 2 == 0:
            secondary = ET.SubElement(action, 'Secondary')
            ET.SubElement(secondary, 'KEY', Information=f'Button {count + index}').text = str(count + index)
    return profile


class SavedProfileTests(unittest.TestCase):
    def test_large_profile_count_builds_action_map_once(self):
        profile = large_profile()
        with patch.object(profile, 'actions', wraps=profile.actions) as actions, \
                patch.object(profile, 'keys', side_effect=AssertionError('Repeated lookup')):
            self.assertEqual(profile.bound_slot_count(), 3300)
            self.assertEqual(actions.call_count, 1)

    def test_large_profile_conflicts_build_action_map_once(self):
        profile = large_profile()
        with patch.object(profile, 'actions', wraps=profile.actions) as actions, \
                patch.object(profile, 'keys', side_effect=AssertionError('Repeated lookup')):
            self.assertEqual(binding_conflicts(profile), {})
            self.assertEqual(actions.call_count, 1)

    def test_count_uses_last_duplicate_action_and_counts_slots_not_chord_keys(self):
        profile = Profile.from_text('<Device><Context ContextName="C"><Action ActionName="A">'
            '<Primary><KEY>0</KEY></Primary></Action><Action ActionName="A">'
            '<Primary><KEY>1</KEY><KEY>2</KEY></Primary><Secondary><KEY>3</KEY></Secondary>'
            '</Action><Action ActionName="B"/></Context></Device>')
        self.assertEqual(profile.bound_slot_count(), 2)

    def test_blank_category_switch_preserves_name_device_axis_settings_and_unknown_fields(self):
        profile = Profile.new('Commercial Airbus Flaps', {'DeviceName': 'Controller', 'GUID': '{0}'}, axes=['X'])
        profile.device.find('Axes/Axis').set('AxisDeadZone', '9')
        ET.SubElement(profile.device, 'FutureField', Value='keep')
        before = semantic_signature(profile.root)
        self.assertTrue(profile.can_change_category())
        profile.change_empty_category('AIRPLANE')
        reopened = Profile.from_text(profile.to_text())
        self.assertEqual(reopened.category, 'AIRPLANE')
        self.assertEqual(reopened.name, 'Commercial Airbus Flaps')
        self.assertEqual(reopened.device.get('GUID'), '{0}')
        self.assertEqual(reopened.device.find('Axes/Axis').get('AxisDeadZone'), '9')
        self.assertEqual(reopened.device.find('FutureField').get('Value'), 'keep')
        profile.change_empty_category('GENERAL')
        self.assertEqual(semantic_signature(profile.root), before)

    def test_existing_actions_or_aircraft_metadata_cannot_be_reclassified(self):
        profiles = [large_profile(1), Profile.from_text('<Device><AircraftInfo CategoryName="AIRPLANE" '
                    'AircraftName="My plane"/></Device>'), Profile.from_text('<DefaultInput><Device/></DefaultInput>')]
        for profile in profiles:
            before = profile.to_text()
            self.assertFalse(profile.can_change_category())
            with self.assertRaises(ValueError):
                profile.change_empty_category('HELICOPTER')
            self.assertEqual(profile.to_text(), before)

    def test_invalid_category_does_not_change_blank_profile(self):
        profile = Profile.new('Test', {'DeviceName': 'Test'})
        before = profile.to_text()
        with self.assertRaises(ValueError):
            profile.change_empty_category('UNKNOWN')
        self.assertEqual(profile.to_text(), before)

    def test_scan_caches_count_and_honors_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'user' / 'container' / 'profile'
            target.parent.mkdir(parents=True)
            profile = large_profile(10)
            profile.save(target)
            self.assertEqual(scan_profiles([folder])[0]['bindings'], 15)
            cancel = threading.Event()
            cancel.set()
            self.assertEqual(scan_profiles([folder], cancel_event=cancel), [])


if __name__ == '__main__':
    unittest.main()
