"""Join English names/categories by exact event ID from MIT-licensed FSProfiles."""
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def friendly(text):
    if text.casefold() == 'meny':
        text = 'Menu'
    acronyms = {'ADF', 'AP', 'ATC', 'COM', 'NAV', 'GPS', 'VOR', 'DME', 'EFB', 'VR', 'IFR', 'VFR',
                'ILS', 'RPM', 'MCDU', 'PFD', 'MFD', 'HUD', 'N1', 'N2'}
    return re.sub(r'\b[A-Za-z0-9]+\b', lambda m: m[0].upper() if m[0].upper() in acronyms else m[0].capitalize(), text)


def main():
    source = Path(sys.argv[1] if len(sys.argv) > 1 else 'data/reference/KnownBindings2024.xml')
    tree = ET.parse(source)
    metadata = {}
    for section in tree.getroot().findall('Section'):
        for subsection in section.findall('SubSection'):
            for action in subsection.findall('SectionAction'):
                for event in action.findall('ActionInput'):
                    name = event.get('InputKey', '')
                    if name.startswith(('KEY_', 'DRONE_KEY_')):
                        metadata.setdefault(name, {'display_name': friendly(action.get('ActionName', name)),
                                        'group': friendly(section.get('SectionName', 'Other controls')),
                                        'subcategory': friendly(subsection.get('SubSectionName', ''))})
    target = Path('data/catalogue.json')
    data = json.loads(target.read_text(encoding='utf-8'))
    matched = 0
    for action in data['actions']:
        if action['name'] in metadata:
            action.update(metadata[action['name']])
            matched += 1
    data['display_metadata_source'] = {'url': 'https://github.com/iadarroch/FSProfiles',
        'commit': 'fec8c2efa289b2bb7e676306f4d383b838a32ac4', 'file': 'FSProfiles/KnownBindings2024.xml',
        'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'license': 'MIT', 'matched_entries': matched}
    target.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps({'matched_action_entries': matched, 'reference_names': len(metadata),
                      'groups': sorted({entry['group'] for entry in metadata.values()})}, indent=2))


if __name__ == '__main__':
    main()
