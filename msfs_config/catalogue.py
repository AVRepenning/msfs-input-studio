import json
import os
from pathlib import Path
import re
import sys


def resource_path(path):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / path


def normalized(name):
    return re.sub(r'[^a-z0-9+-]', '', name.casefold())


def device_family(device):
    name = device.get('DeviceName', '').casefold()
    if 'keyboard' in name:
        return 'keyboard'
    if name == 'mouse' or name.startswith('mouse '):
        return 'mouse'
    if 'xinput' in name or name == 'gamepad' or 'dualsense' in name:
        return 'gamepad'
    return 'joystick'


def input_identity(name, family):
    # Keyboard punctuation is an input, not formatting to strip.
    return name.strip().casefold() if family == 'keyboard' else normalized(name)


class Catalogue:
    def __init__(self, path=None, storage=False):
        data = json.loads(Path(path or resource_path('data/catalogue.json')).read_text(encoding='utf-8'))
        self.actions = {(a['context'], a['name']): a for a in data['actions']}
        self.key_pairs = {k['information']: k['id'] for k in data['keys']}
        self.conflicts = set()
        self.scoped_keys = {'joystick': dict(self.key_pairs)}
        self.scoped_conflicts = {'joystick': set()}
        self.storage = (Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio' / 'learned_catalogue.json') if storage is True else Path(storage) if storage else None
        self.library_warning = ''
        if self.storage and self.storage.is_file():
            try:
                saved = json.loads(self.storage.read_text(encoding='utf-8'))
                for entry in saved.get('actions', []):
                    if not all(isinstance(entry.get(k), str) for k in ('context', 'name')):
                        raise ValueError('Invalid saved action')
                    identity = (entry['context'], entry['name'])
                    old = self.actions.setdefault(identity, entry)
                    old['categories'] = sorted(set(old['categories'] + entry['categories']))
                    for field in ('display_name', 'description', 'group', 'subcategory', 'tag'):
                        if field in entry:
                            old[field] = entry[field]
                for name, value in saved.get('keys', {}).items():
                    if not isinstance(name, str) or not isinstance(value, int) or value < 0:
                        raise ValueError('Invalid saved input ID')
                    if name in self.key_pairs and self.key_pairs[name] != value:
                        self.conflicts.add(normalized(name))
                    else:
                        self.key_pairs[name] = value
                self.conflicts.update(saved.get('conflicts', []))
                if 'scoped_keys' not in saved:
                    # v0.1 learned only DirectInput joystick references.
                    self.scoped_keys['joystick'] = dict(self.key_pairs)
                    self.scoped_conflicts['joystick'].update(self.conflicts)
                for family, pairs in saved.get('scoped_keys', {}).items():
                    target = self.scoped_keys.setdefault(family, {})
                    for name, value in pairs.items():
                        if not isinstance(name, str) or not isinstance(value, int) or value < 0:
                            raise ValueError('Invalid device-scoped input ID')
                        if name in target and target[name] != value:
                            self.scoped_conflicts.setdefault(family, set()).add(input_identity(name, family))
                        else:
                            target[name] = value
                for family, conflicts in saved.get('scoped_conflicts', {}).items():
                    self.scoped_conflicts.setdefault(family, set()).update(conflicts)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.library_warning = f'Could not load the learned catalogue: {exc}'
        self._index()

    def _index(self):
        self.index = {}
        for name, value in self.key_pairs.items():
            key = normalized(name)
            if key not in self.index:
                self.index[key] = (name, value)
            elif self.index[key] is None or self.index[key][1] != value:
                self.index[key] = None
                self.conflicts.add(key)
        for key in self.conflicts:
            self.index[key] = None
        self.scoped_indexes = {}
        for family, pairs in self.scoped_keys.items():
            index = {}
            quarantined = self.scoped_conflicts.setdefault(family, set())
            for name, value in pairs.items():
                key = input_identity(name, family)
                if key in index and (index[key] is None or index[key][1] != value):
                    quarantined.add(key)
                else:
                    index[key] = (name, value)
            for key in quarantined:
                index[key] = None
            self.scoped_indexes[family] = index

    def resolve(self, name, family=None):
        if family is not None:
            return self.scoped_indexes.get(family, {}).get(input_identity(name, family))
        return self.index.get(normalized(name))

    def keys_for(self, family):
        return self.scoped_keys.get(family, {})

    def learn(self, profile):
        family = device_family(profile.device.attrib)
        scoped = self.scoped_keys.setdefault(family, {})
        quarantined = self.scoped_conflicts.setdefault(family, set())
        for (ctx, name), action in profile.actions().items():
            entry = self.actions.setdefault((ctx, name), {'context': ctx, 'name': name,
                    'categories': [], 'attributes': dict(action.attrib)})
            if profile.category not in entry['categories']:
                entry['categories'].append(profile.category)
        for key in profile.device.findall('.//KEY'):
            name = key.get('Information', '')
            value = (key.text or '').strip()
            if name and value.isdigit():
                old_scoped = self.resolve(name, family)
                if old_scoped and old_scoped[1] != int(value):
                    quarantined.add(input_identity(name, family))
                elif name in scoped and scoped[name] != int(value):
                    quarantined.add(input_identity(name, family))
                else:
                    scoped[name] = int(value)
                old = self.resolve(name)
                if old and old[1] != int(value):
                    self.conflicts.add(normalized(name))
                elif name in self.key_pairs and self.key_pairs[name] != int(value):
                    self.conflicts.add(normalized(name))
                else:
                    self.key_pairs[name] = int(value)
        self._index()

    def save_library(self):
        if self.storage:
            self.storage.parent.mkdir(parents=True, exist_ok=True)
            staging = self.storage.with_suffix('.tmp')
            staging.write_text(json.dumps({'actions': list(self.actions.values()),
                                'keys': self.key_pairs, 'conflicts': sorted(self.conflicts),
                                'scoped_keys': self.scoped_keys,
                                'scoped_conflicts': {family: sorted(keys) for family, keys in self.scoped_conflicts.items()}}, indent=2), encoding='utf-8')
            staging.replace(self.storage)

    def learn_actiondb(self, document, category):
        if document.root.tag != 'ActionDefinition':
            raise ValueError('Choose an ActionDefinition database to import controls.')
        errors = document.validate()
        if errors:
            raise ValueError('\n'.join(errors[:12]))
        count = 0
        for action in document.root.findall('Actions/Action'):
            context, name = action.findtext('Context'), action.findtext('Name')
            entry = self.actions.setdefault((context, name), {'context': context, 'name': name,
                          'categories': [], 'attributes': {'Flag': '4' if action.findtext('Type') == 'AXIS' else '2',
                                                          'ValueEvent': '0', 'Delay': '0'}})
            if category not in entry['categories']:
                entry['categories'].append(category)
            for xml, field in [('TT_Name', 'display_name'), ('TT_Description', 'description'),
                               ('TT_Function', 'description'), ('TT_Category_Main', 'group'),
                               ('TT_Category_Sub', 'subcategory'), ('TT_Tag', 'tag')]:
                value = action.findtext(xml, '')
                if value and not value.startswith('TT:'):
                    entry[field] = value
            count += 1
        return count


def display_name(name):
    return re.sub(r'^(KEY_|DRONE_KEY_)', '', name).replace('_', ' ').title()
