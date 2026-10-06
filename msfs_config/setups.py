"""One controller setup containing independent, lossless simulator profile layers."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

from .catalogue import device_family
from .profiles import Profile


def controller_key(profile):
    device = profile.device.attrib
    return (device_family(device), device.get('GUID', '').lower(), device.get('CompositeID', '0'))


def category_layer(profile):
    info = profile.device.find('AircraftInfo')
    return profile.format == 'native' and (info is None or (set(info.attrib) <= {'CategoryName'} and not len(info)))


@dataclass
class Layer:
    profile: Profile
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    editor: dict = field(default_factory=dict)


class ControllerSetup:
    def __init__(self, profile, name=None):
        self.id = str(uuid.uuid4())
        self.name = name or profile.name
        self.layers = []
        self.active_id = None
        self.add(profile)

    @property
    def active(self):
        return next(layer for layer in self.layers if layer.id == self.active_id)

    def add(self, profile):
        if self.layers and controller_key(profile) != controller_key(self.layers[0].profile):
            raise ValueError('Every profile in a setup must belong to the same controller and input format.')
        layer = Layer(profile)
        self.layers.append(layer)
        self.active_id = layer.id
        return layer

    def category(self, category):
        return next((layer for layer in reversed(self.layers) if layer.profile.category == category
                     and category_layer(layer.profile)), None)

    def ensure_category(self, category):
        existing = self.category(category)
        if existing:
            return existing
        source = self.active.profile
        if source.format != 'native':
            raise ValueError('SDK source documents are edited separately; open a native export for a simulator setup.')
        profile = Profile.new(source.name, dict(source.device.attrib), category)
        axes = source.device.find('Axes')
        if axes is not None:
            from copy import deepcopy
            profile.device.remove(profile.device.find('Axes'))
            profile.device.append(deepcopy(axes))
        active = self.active_id
        layer = self.add(profile)
        self.active_id = active
        return layer

    def to_dict(self, labels=None):
        if not self.layers or any(controller_key(layer.profile) != controller_key(self.layers[0].profile) for layer in self.layers):
            raise ValueError('All setup profiles must target the same controller.')
        return {'schema': 1, 'id': self.id, 'name': self.name, 'active': self.active_id,
                'layers': [{'id': layer.id, 'profile_xml': layer.profile.to_text()} for layer in self.layers],
                'controller_labels': labels or {}}

    def save(self, path, labels=None):
        path = Path(path)
        staging = path.with_name(path.name + '.tmp')
        staging.write_text(json.dumps(self.to_dict(labels), indent=2), encoding='utf-8')
        staging.replace(path)

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 100_000_000:
            raise ValueError('Controller setup is too large (limit: 100 MB).')
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get('layers'), list) or not 1 <= len(data['layers']) <= 100:
            raise ValueError('Unsupported or invalid controller setup.')
        if any(not isinstance(data.get(name), str) for name in ('id', 'name', 'active')) or any(
            not isinstance(row, dict) or not isinstance(row.get('id'), str) or not isinstance(row.get('profile_xml'), str) for row in data['layers']):
            raise ValueError('Invalid setup fields or XML profile data.')
        uuid.UUID(data['id'])
        first = data['layers'][0]
        setup = cls(Profile.from_text(first['profile_xml']), data['name'])
        setup.id, setup.layers = data['id'], []
        used = set()
        for row in data['layers']:
            uuid.UUID(row['id'])
            if row['id'] in used:
                raise ValueError('Duplicate profile layer in controller setup.')
            used.add(row['id'])
            layer = setup.add(Profile.from_text(row['profile_xml']))
            layer.id = row['id']
        if data['active'] not in used:
            raise ValueError('The active profile is missing from the setup.')
        setup.active_id = data['active']
        labels = data.get('controller_labels', {})
        if not isinstance(labels, dict) or any(not isinstance(guid, str) or not isinstance(names, dict) or
                 any(not isinstance(name, str) or not isinstance(label, str) for name, label in names.items()) for guid, names in labels.items()):
            raise ValueError('Invalid input names in controller setup.')
        return setup, labels

    def export(self, folder):
        self.to_dict()
        folder = Path(folder)
        from .local_profiles import is_managed_save
        if is_managed_save(folder):
            raise ValueError('Export outside the simulator’s managed saves, then import through MSFS Controls.')
        for layer in self.layers:
            errors = layer.profile.validate()
            if layer.profile.format != 'native':
                errors.append('SDK source XML must be built separately; it is not a Controls-menu import.')
            if errors:
                raise ValueError(f'{layer.profile.name}: ' + '\n'.join(errors[:6]))
        folder.mkdir(parents=True, exist_ok=True)
        used, files, instructions = set(), [], []
        for layer in self.layers:
            profile = layer.profile
            base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', profile.name + ' - ' + profile.category.title()).strip('. ')[:130] or 'Controller'
            name, number = base + '.xml', 2
            while name.casefold() in used or (folder / name).exists():
                name = f'{base} ({number}).xml'
                number += 1
            used.add(name.casefold())
            path = folder / name
            profile.save(path)
            files.append(path)
            scope = 'Specific aircraft controls' if not category_layer(profile) else profile.category.title() + ' controls'
            instructions.append(f'- {path.name}: import under {scope} for {profile.device.get("DeviceName")}.')
        guide = folder / 'IMPORT-SETUP.txt'
        number = 2
        while guide.exists():
            guide = folder / f'IMPORT-SETUP-{number}.txt'
            number += 1
        guide.write_text('Import this controller setup into MSFS 2024\n\n'
            'Settings > Controls > select the SAME controller. Import each XML using the cogwheel for its matching profile type.\n'
            + '\n'.join(instructions) + '\n\nSelect one preset for each profile type. General camera/menu bindings and the chosen aircraft flight bindings work at the same time. Multiple presets of the same type are alternatives.\n'
            'The simulator requires separate XML profiles for these layers; do not combine their actions into one Airplane XML.\n', encoding='utf-8')
        return files, guide


class SetupStore:
    def __init__(self, storage=True):
        self.folder = Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio/setups' if storage is True else Path(storage) if storage else None

    def save(self, setup, labels=None):
        if self.folder:
            uuid.UUID(setup.id)
            self.folder.mkdir(parents=True, exist_ok=True)
            setup.save(self.folder / (setup.id + '.msfssetup'), labels)

    def entries(self):
        rows = []
        if self.folder:
            for path in self.folder.glob('*.msfssetup'):
                try:
                    setup, labels = ControllerSetup.load(path)
                    rows.append({'setup': setup, 'labels': labels, 'path': path,
                                 'updated': datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
                except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
                    continue
        return sorted(rows, key=lambda row: row['updated'], reverse=True)
