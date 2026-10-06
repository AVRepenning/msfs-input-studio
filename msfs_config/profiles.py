"""Lossless semantic editing of SDK XML and MSFS rootless export documents."""
from copy import deepcopy
import math
from pathlib import Path
import re
import uuid
import xml.etree.ElementTree as ET

AXES = ('X', 'Y', 'Z', 'rX', 'rY', 'rZ', 'SliderX', 'SliderY')
AXIS_DEFAULTS = {'AxisSensitivy': '0', 'AxisSensitivyMinus': '0', 'AxisDeadZone': '0',
                 'AxisOutDeadZone': '0', 'AxisNeutral': '0', 'AxisResponseRate': '-1'}
FLAGS = {1: 'Analog', 2: 'Digital', 4: 'Axis', 8: 'No modifier', 16: 'Ctrl',
         32: 'Shift', 64: 'Alt', 128: 'Invert', 256: 'On release', 512: 'Send value',
         1024: 'Ignore sensitivity curve', 2048: 'Context reset modifier',
         4096: 'Override axis', 8192: 'Once on press', 16384: 'Delayed / hold',
         32768: 'Raw keyboard layout'}


def parse_document(text):
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('XML with DTDs or entities is not a controller profile.')
    text = re.sub(r'<\?xml[^>]*\?>', '', text).strip()
    root = ET.fromstring('<ProfileDocument>' + text + '</ProfileDocument>',
                         parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True)))
    if root.find('Device') is not None:
        return root, 'native'
    if root.find('DefaultInput/Device') is not None:
        return root, 'sdk'
    raise ValueError('Expected a native MSFS export or a DefaultInput SDK profile.')


class Profile:
    def __init__(self, root, format='native'):
        self.root, self.format = root, format

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > 20_000_000:
            raise ValueError('Profile file is too large (limit: 20 MB).')
        return cls(*parse_document(path.read_text(encoding='utf-8-sig')))

    @classmethod
    def from_text(cls, text):
        return cls(*parse_document(text))

    @classmethod
    def new(cls, name, device, category='GENERAL', axes=()):
        root = ET.Element('ProfileDocument')
        ET.SubElement(root, 'Version', Num='-1')
        ET.SubElement(root, 'FriendlyName', PlatformAvailability='1', Locked='false').text = name
        node = ET.SubElement(root, 'Device', **device)
        if category != 'GENERAL':
            ET.SubElement(node, 'AircraftInfo', CategoryName=category)
        group = ET.SubElement(node, 'Axes')
        for axis in axes:
            ET.SubElement(group, 'Axis', AxisName=axis, **AXIS_DEFAULTS)
        return cls(root)

    @property
    def container(self):
        return self.root if self.format == 'native' else self.root.find('DefaultInput')

    @property
    def device(self):
        return self.container.find('Device')

    @property
    def name(self):
        node = self.container.find('FriendlyName')
        return node.text or '' if node is not None else self.device.get('DeviceName', 'Profile')

    @name.setter
    def name(self, value):
        node = self.container.find('FriendlyName')
        if node is None:
            if self.format == 'sdk':
                return  # FriendlyName is not part of the SDK DefaultInput schema.
            node = ET.Element('FriendlyName', PlatformAvailability='1', Locked='false')
            self.container.insert(1, node)
        node.text = value

    @property
    def category(self):
        info = self.device.find('AircraftInfo')
        return info.get('CategoryName', 'GENERAL') if info is not None else 'GENERAL'

    def actions(self):
        return {(ctx.get('ContextName'), action.get('ActionName')): action
                for ctx in self.device.findall('Context') for action in ctx.findall('Action')}

    def bound_slot_count(self):
        return sum(bool(action.findall(f'{slot}/KEY'))
                   for action in self.actions().values() for slot in ('Primary', 'Secondary'))

    def can_change_category(self):
        info = self.device.find('AircraftInfo')
        return (self.format == 'native' and not self.actions() and
                (info is None or (set(info.attrib) <= {'CategoryName'} and not len(info)
                                  and not (info.text or '').strip())))

    def change_empty_category(self, category):
        if category not in ('GENERAL', 'AIRPLANE', 'HELICOPTER') or not self.can_change_category():
            raise ValueError('Create a separate profile to change the type of an existing aircraft or control profile.')
        info = self.device.find('AircraftInfo')
        if info is not None:
            self.device.remove(info)
        if category != 'GENERAL':
            self.device.insert(0, ET.Element('AircraftInfo', CategoryName=category))

    def action(self, context, name, create=False, defaults=None):
        found = self.actions().get((context, name))
        if found is not None or not create:
            return found
        ctx = next((c for c in self.device.findall('Context') if c.get('ContextName') == context), None)
        if ctx is None:
            ctx = ET.SubElement(self.device, 'Context', ContextName=context)
        attrs = dict(defaults or {'Flag': '2', 'ValueEvent': '0.000000', 'Delay': '0.000000'})
        attrs['ActionName'] = name
        return ET.SubElement(ctx, 'Action', **attrs)

    def set_binding(self, context, name, slot, keys, defaults=None):
        if slot not in ('Primary', 'Secondary'):
            raise ValueError('Invalid binding slot.')
        keys = list(keys)
        if any(not information or not str(value).isdigit() for information, value in keys):
            raise ValueError('Only verified numeric input IDs can be bound.')
        action = self.action(context, name, create=True, defaults=defaults)
        binding = action.find(slot)
        if binding is None and keys:
            binding = ET.SubElement(action, slot)
        if binding is None:
            return
        for node in list(binding):
            if node.tag == 'KEY' or (not keys and node.tag == 'Axis'):
                binding.remove(node)
        for index, (information, value) in enumerate(keys):
            node = ET.Element('KEY', Information=information)
            node.text = str(value)
            binding.insert(index, node)
        if not len(binding):
            action.remove(binding)
        if not keys and not action.findall('./Primary/Axis') and not action.findall('./Secondary/Axis'):
            action.set('Flag', str(int(action.get('Flag', '2')) & ~4096))

    def keys(self, context, name, slot):
        action = self.action(context, name)
        binding = action.find(slot) if action is not None else None
        return [(k.get('Information', ''), k.text or '') for k in binding.findall('KEY')] if binding is not None else []

    def set_axis(self, axis, values, action=None, slot='Primary'):
        if axis not in self.axis_names():
            raise ValueError('Choose a standard axis or an axis present in this imported profile.')
        validate_axis(values)
        if action is None:
            parent = self.device.find('Axes')
            if parent is None:
                parent = ET.SubElement(self.device, 'Axes')
        else:
            parent = action.find(slot)
            if parent is None or not parent.findall('KEY'):
                raise ValueError('Bind an input before setting its axis override.')
        node = next((a for a in parent.findall('Axis') if a.get('AxisName') == axis), None)
        if node is None:
            node = ET.SubElement(parent, 'Axis', AxisName=axis)
        node.attrib.update({k: str(v) for k, v in values.items()})

    def axis_names(self):
        observed = dict.fromkeys(node.get('AxisName') for node in self.device.findall('.//Axis') if node.get('AxisName'))
        # GameInput profiles can use numeric axes. Retain their exact identities;
        # their ordinals are not a verified mapping to DirectInput X/Y/etc.
        numeric = [name for name in observed if name.isdecimal()]
        return tuple(sorted(numeric, key=int)) + tuple(name for name in observed if name not in numeric) if numeric else tuple(dict.fromkeys((*AXES, *observed)))

    def validate(self):
        errors = []
        try:
            from .catalogue import device_family
            guid = self.device.get('GUID', '')
            builtin = self.format == 'native' and guid == '{0}' and device_family(self.device.attrib) in ('keyboard', 'mouse', 'gamepad')
            if not builtin:
                uuid.UUID(guid.strip('{}'))
        except ValueError:
            errors.append('The device GUID is missing or invalid. Select a connected device or open a real export.')
        for field in ('DeviceName', 'ProductID', 'CompositeID', 'HWVer'):
            if not self.device.get(field):
                errors.append(f'The device {field} is missing.')
        for key in self.device.findall('.//KEY'):
            if not key.get('Information') or not (key.text or '').strip().isdigit():
                errors.append('A binding has an unresolved input name or numeric ID.')
        for action in self.actions().values():
            try:
                flag = int(action.get('Flag', '2'))
                if flag < 0:
                    raise ValueError()
                for attr in ('Delay', 'ValueEvent'):
                    if not math.isfinite(float(action.get(attr, '0'))):
                        raise ValueError()
                if float(action.get('Delay', '0')) < 0:
                    raise ValueError()
            except ValueError:
                errors.append(f'Invalid flags, delay or value for {action.get("ActionName")}.')
        for axis in self.device.findall('.//Axis'):
            try:
                validate_axis(axis.attrib)
            except ValueError as exc:
                errors.append(str(exc))
        return errors

    def to_text(self):
        root = deepcopy(self.root)
        ET.indent(root, space='\t')
        # Native MSFS exports deliberately have several top-level elements.
        # Do not serialize the internal parsing wrapper into the file.
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(
            ET.tostring(child, encoding='unicode').strip() for child in root) + '\n'

    def save(self, path):
        errors = self.validate()
        if errors:
            raise ValueError('\n'.join(errors[:12]))
        path = Path(path)
        staging = path.with_name(path.name + '.tmp')
        staging.write_text(self.to_text(), encoding='utf-8')
        staging.replace(path)


def validate_axis(values):
    # Real 2024 exports contain positive AND negative values on both sides.
    # SDK reference ranges differ; preserve the range observed in the runtime UI.
    for name in ('AxisSensitivy', 'AxisSensitivyMinus', 'AxisNeutral'):
        value = int(values.get(name, '0'))
        if not -100 <= value <= 100:
            raise ValueError(f'{name} must be between -100 and 100.')
    for name in ('AxisDeadZone', 'AxisOutDeadZone'):
        if not 0 <= int(values.get(name, '0')) <= 100:
            raise ValueError(f'{name} must be between 0 and 100.')
    response = int(values.get('AxisResponseRate', '-1'))
    if response != -1 and not 100 <= response <= 2000:
        raise ValueError('Response rate must be -1 (default) or 100–2000.')


def semantic_signature(node):
    return (str(node.tag), tuple(sorted(node.attrib.items())), (node.text or '').strip(),
            tuple(semantic_signature(child) for child in node))
