"""Local working copies, separate from simulator exports and managed cloud saves."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from .profiles import Profile


class DraftStore:
    def __init__(self, storage=True):
        self.folder = Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio/drafts' if storage is True else Path(storage) if storage else None

    def save(self, session, profile, labels):
        if not self.folder:
            return
        uuid.UUID(session)
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / (session + '.json')
        data = {'schema': 1, 'updated': datetime.now(timezone.utc).isoformat(),
                'profile_xml': profile.to_text(), 'controller_labels': labels}
        staging = path.with_suffix('.tmp')
        staging.write_text(json.dumps(data, indent=2), encoding='utf-8')
        staging.replace(path)

    def entries(self):
        rows = []
        if self.folder:
            for path in self.folder.glob('*.json'):
                try:
                    if path.stat().st_size > 25_000_000:
                        continue
                    data = json.loads(path.read_text(encoding='utf-8'))
                    profile = Profile.from_text(data['profile_xml'])
                    rows.append({'id': path.stem, 'updated': data['updated'], 'profile': profile,
                                 'labels': data.get('controller_labels', {})})
                except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
                    continue
        return sorted(rows, key=lambda row: row['updated'], reverse=True)
