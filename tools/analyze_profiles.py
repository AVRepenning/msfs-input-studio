"""Reproduce the bundled catalogue using the public repository from the handoff."""
import collections
import hashlib
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SOURCE = 'https://github.com/highinthefssky/msfs-2024-controls-settings'


def parse(path):
    text = path.read_text(encoding='utf-8-sig')
    text = re.sub(r'<\?xml[^>]*\?>', '', text)
    return ET.fromstring('<ProfileDocument>' + text + '</ProfileDocument>')


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else 'research/community-profiles/profiles')
    actions = {}
    unbound_templates = set()
    keys = collections.defaultdict(collections.Counter)
    key_sources = collections.defaultdict(list)
    sources = []
    categories = collections.Counter()
    for path in sorted(folder.glob('*.xml')):
        root = parse(path)
        device = root.find('.//Device')
        info = device.find('AircraftInfo')
        category = info.get('CategoryName', 'GENERAL') if info is not None else 'GENERAL'
        categories[category] += 1
        sources.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        for ctx in device.findall('Context'):
            for act in ctx.findall('Action'):
                identity = (ctx.get('ContextName'), act.get('ActionName'))
                entry = actions.setdefault(identity, {'context': identity[0], 'name': identity[1], 'categories': [], 'attributes': dict(act.attrib)})
                # Prefer the simulator's unbound defaults over another user's
                # custom hold/release/value behavior for the new-profile UI.
                if not act.findall('.//KEY') and identity not in unbound_templates:
                    entry['attributes'] = dict(act.attrib)
                    unbound_templates.add(identity)
                if category not in entry['categories']:
                    entry['categories'].append(category)
        for key in device.findall('.//KEY'):
            name, value = key.get('Information'), (key.text or '').strip()
            if name and value.isdigit():
                keys[name][value] += 1
                if path.name not in key_sources[name]:
                    key_sources[name].append(path.name)
    learned = [{'information': name, 'id': int(next(iter(counts))), 'sources': key_sources[name]}
               for name, counts in sorted(keys.items()) if len(counts) == 1]
    conflicts = {name: dict(counts) for name, counts in keys.items() if len(counts) > 1}
    data = {'source': SOURCE, 'license': 'GPL-3.0', 'sources': sources,
            'actions': sorted(actions.values(), key=lambda a: (a['context'], a['name'])),
            'keys': learned, 'conflicts': conflicts,
            'note': 'Observed in exported DirectInput profiles; no key IDs extrapolated. Action coverage is limited to these exports.'}
    out = Path('data/catalogue.json')
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps({'files': len(sources), 'categories': dict(categories), 'actions': len(actions), 'keys': len(learned), 'conflicts': conflicts}, indent=2))


if __name__ == '__main__':
    main()
