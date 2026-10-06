import json
import os
from pathlib import Path
import re
import sys


def resource_path(path):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / path


def normalized(name):
    return re.sub(r'[^a-z0-9+-]', '', name.casefold())


class Catalogue:
    def __init__(self, path=None, storage=False):
        data = json.loads(Path(path or resource_path('data/catalogue.json')).read_text(encoding='utf-8'))
        self.actions = {(a['context'], a['name']): a for a in data['actions']}
        self.key_pairs = {k['information']: k['id'] for k in data['keys']}
        self.conflicts = set()
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
                for name, value in saved.get('keys', {}).items():
                    if not isinstance(name, str) or not isinstance(value, int) or value < 0:
                        raise ValueError('Invalid saved input ID')
                    if name in self.key_pairs and self.key_pairs[name] != value:
                        self.conflicts.add(normalized(name))
                    else:
                        self.key_pairs[name] = value
                self.conflicts.update(saved.get('conflicts', []))
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

    def resolve(self, name):
        return self.index.get(normalized(name))

    def learn(self, profile):
        for (ctx, name), action in profile.actions().items():
            entry = self.actions.setdefault((ctx, name), {'context': ctx, 'name': name,
                    'categories': [], 'attributes': dict(action.attrib)})
            if profile.category not in entry['categories']:
                entry['categories'].append(profile.category)
        for key in profile.device.findall('.//KEY'):
            name = key.get('Information', '')
            value = (key.text or '').strip()
            if name and value.isdigit():
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
                                'keys': self.key_pairs, 'conflicts': sorted(self.conflicts)}, indent=2), encoding='utf-8')
            staging.replace(self.storage)


def display_name(name):
    return re.sub(r'^(KEY_|DRONE_KEY_)', '', name).replace('_', ' ').title()
