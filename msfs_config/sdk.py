"""SDK source documents. These require the MSFS SDK build pipeline for deployment."""
from copy import deepcopy
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ACTION_FIELDS = ('Name', 'Context', 'Type', 'TT_Name', 'TT_Function', 'TT_Description',
                 'TT_Category_Main', 'TT_Category_Sub', 'TT_Tag')
ATTRIBUTES = {
    'Device': ('ProductID', 'CompositeID', 'DisplayName', 'TextureFolder', 'Priority', 'Platform'),
    'MergeIcons': ('SourceIcons', 'TargetIcon', 'TargetTT'), 'ButtonTT': ('buttonId', 'TT'),
    'MetaContext': ('Name',), 'Context': ('ID',), 'RemapAction': ('str', 'player')}
CHILDREN = {'DeviceConfig': ('Device',), 'Device': ('ButtonTT', 'MergeIcons'),
            'ActionDefinition': ('MetaContexts', 'Actions'), 'MetaContexts': ('MetaContext',),
            'MetaContext': ('Context',), 'Actions': ('Action',), 'RemapActions': ('RemapAction',),
            'RemapAction': ('InputAction',), 'InputAction': ('Input',)}


class SDKDocument:
    def __init__(self, root):
        if root.tag not in ('DeviceConfig', 'ActionDefinition', 'RemapActions'):
            raise ValueError('Expected DeviceConfig, ActionDefinition or RemapActions XML.')
        self.root = root

    @classmethod
    def from_text(cls, text):
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
            raise ValueError('DTDs and entities are not supported in SDK sources.')
        return cls(ET.fromstring(text, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))))

    @classmethod
    def load(cls, path):
        if Path(path).stat().st_size > 20_000_000:
            raise ValueError('SDK source is too large (limit: 20 MB).')
        return cls.from_text(Path(path).read_text(encoding='utf-8-sig'))

    @classmethod
    def new(cls, kind):
        root = ET.Element(kind)
        if kind == 'ActionDefinition':
            ET.SubElement(root, 'MetaContexts')
            ET.SubElement(root, 'Actions')
        return cls(root)

    @classmethod
    def device_config(cls, device, labels, catalogue):
        from .catalogue import device_family
        family = device_family(device.attributes)
        label_guid = device.instance_guid + ':' + family if device.instance_guid == '{0}' else device.instance_guid
        doc = cls.new('DeviceConfig')
        node = ET.SubElement(doc.root, 'Device', ProductID=f'0x{device.product_id:04X}',
                             CompositeID='0', DisplayName=device.name, TextureFolder='controller', Platform='PC')
        seen = set()
        for obj in device.objects:
            names = [obj.msfs_name()]
            if obj.kind == 'axis':
                names += [obj.msfs_name('+'), obj.msfs_name('-')]
            if obj.kind == 'pov':
                from .devices import POV_DIRECTIONS
                names += [obj.msfs_name(d) for d in POV_DIRECTIONS]
            label = labels.get(label_guid, obj.msfs_name()) or obj.name
            for name in names:
                pair = catalogue.resolve(name, family)
                if pair and pair[0].strip() not in seen:
                    seen.add(pair[0].strip())
                    ET.SubElement(node, 'ButtonTT', buttonId=pair[0].strip(), TT=labels.get(label_guid, name) or label)
        return doc

    def validate(self):
        errors = []
        if self.root.tag == 'DeviceConfig':
            for device in self.root.findall('Device'):
                for name in ('ProductID', 'DisplayName', 'TextureFolder'):
                    if not device.get(name, '').strip():
                        errors.append(f'Device: {name} is required.')
                if not re.fullmatch(r'0x[0-9a-fA-F]+', device.get('ProductID', '')):
                    errors.append('Device ProductID must be hexadecimal with a 0x prefix.')
                for name in ('CompositeID', 'Priority'):
                    if name in device.attrib:
                        try:
                            int(device.get(name))
                        except ValueError:
                            errors.append(f'Device {name} must be an integer.')
                for tag in ('MergeIcons', 'ButtonTT'):
                    for child in device.findall(tag):
                        for name in ATTRIBUTES[tag]:
                            if name not in child.attrib or (name != 'TargetTT' and not child.get(name).strip()):
                                errors.append(f'{tag}: {name} is required.')
        elif self.root.tag == 'ActionDefinition':
            seen = set()
            for action in self.root.findall('Actions/Action'):
                identity = (action.findtext('Context', ''), action.findtext('Name', ''))
                if not all(identity) or not re.fullmatch(r'[A-Za-z0-9_-]+', identity[1]):
                    errors.append('Action requires a context and an alphanumeric event name (underscore/hyphen allowed).')
                if identity in seen:
                    errors.append('Duplicate action: ' + identity[1])
                seen.add(identity)
                if action.findtext('Type') not in ('DIGITAL', 'AXIS'):
                    errors.append('Action Type must be DIGITAL or AXIS.')
                for field in ('TT_Name', 'TT_Category_Main', 'TT_Category_Sub'):
                    if action.find(field) is None:
                        errors.append('Action requires ' + field)
        elif self.root.tag == 'RemapActions':
            for remap in self.root.findall('RemapAction'):
                if not remap.get('str', '').startswith('STR_') or remap.get('player', '').upper() != 'ALL':
                    errors.append('Remap requires a STR_ UI string and player ALL.')
                if not remap.findall('InputAction'):
                    errors.append('Remap requires at least one InputAction alternative.')
                for alternative in remap.findall('InputAction'):
                    if not alternative.findall('Input') or any(not (n.text or '').strip() for n in alternative.findall('Input')):
                        errors.append('Each InputAction requires one or more nonempty Input names.')
        return errors

    def to_text(self):
        root = deepcopy(self.root)
        ET.indent(root, space='  ')
        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='unicode') + '\n'

    def save(self, path):
        errors = self.validate()
        if errors:
            raise ValueError('\n'.join(errors[:12]))
        target = Path(path)
        staging = target.with_name(target.name + '.tmp')
        staging.write_text(self.to_text(), encoding='utf-8')
        staging.replace(target)
