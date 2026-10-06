from pathlib import Path
import tempfile
import unittest
import uuid

from msfs_config.drafts import DraftStore
from msfs_config.profiles import Profile


class DraftTests(unittest.TestCase):
    def profile(self):
        profile = Profile.new('Work in progress', {'DeviceName': 'Keyboard', 'GUID': '{0}',
                              'ProductID': '34891', 'CompositeID': '0', 'HWVer': '1.0.0.0'})
        profile.set_binding('TEST', 'MY_ACTION', 'Primary', [('A', 65)])
        return profile

    def test_working_copy_keeps_binding_identity_and_aliases(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DraftStore(folder)
            session = str(uuid.uuid4())
            profile = self.profile()
            store.save(session, profile, {'{0}:keyboard': {'a': 'Landing gear'}})
            profile.name = 'Updated working copy'
            store.save(session, profile, {'{0}:keyboard': {'a': 'Landing gear'}})
            rows = store.entries()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['id'], session)
            self.assertEqual(rows[0]['profile'].name, 'Updated working copy')
            self.assertEqual(rows[0]['profile'].keys('TEST', 'MY_ACTION', 'Primary'), [('A', '65')])
            self.assertEqual(rows[0]['labels']['{0}:keyboard']['a'], 'Landing gear')

    def test_corrupt_working_copy_does_not_hide_other_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            store = DraftStore(folder)
            store.save(str(uuid.uuid4()), self.profile(), {})
            (Path(folder) / 'bad.json').write_text('{"profile_xml":"<bad","updated":"now"}', encoding='utf-8')
            self.assertEqual(len(store.entries()), 1)

    def test_invalid_binding_edit_preserves_previous_binding(self):
        profile = self.profile()
        original = profile.to_text()
        with self.assertRaises(ValueError):
            profile.set_binding('TEST', 'MY_ACTION', 'Primary', [('Unknown', 'pending')])
        self.assertEqual(profile.to_text(), original)

    def test_clearing_axis_binding_removes_its_override_and_keeps_secondary(self):
        profile = self.profile()
        action = profile.action('TEST', 'MY_ACTION')
        profile.set_axis('X', {'AxisDeadZone': '9'}, action)
        action.set('Flag', '4100')
        profile.set_binding('TEST', 'MY_ACTION', 'Secondary', [('B', 66)])
        profile.set_binding('TEST', 'MY_ACTION', 'Primary', [])
        self.assertIsNone(action.find('Primary'))
        self.assertFalse(int(action.get('Flag')) & 4096)
        self.assertEqual(profile.keys('TEST', 'MY_ACTION', 'Secondary'), [('B', '66')])


if __name__ == '__main__':
    unittest.main()
