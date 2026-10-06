"""User-facing controller labels, independent of simulator input identities."""
import json
import os
from pathlib import Path

from .catalogue import normalized, input_identity


class ControllerLabels:
    @staticmethod
    def input_key(guid, name):
        return input_identity(name, 'keyboard') if guid.endswith(':keyboard') else normalized(name)
    def __init__(self, storage=True):
        self.path = (Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio/controller_labels.json') if storage is True else Path(storage) if storage else None
        self.devices = {}
        if self.path and self.path.is_file():
            try:
                self.merge(json.loads(self.path.read_text(encoding='utf-8')))
            except (OSError, ValueError, TypeError):
                pass

    def merge(self, data):
        if not isinstance(data, dict):
            raise ValueError('Controller labels must be a dictionary.')
        for guid, labels in data.items():
            if not isinstance(guid, str) or not isinstance(labels, dict):
                raise ValueError('Invalid controller labels.')
            for name, label in labels.items():
                if not isinstance(name, str) or not isinstance(label, str) or len(label) > 120:
                    raise ValueError('Invalid input label.')
                self.devices.setdefault(guid.lower(), {})[self.input_key(guid, name)] = label

    def get(self, guid, input_name):
        labels = self.devices.get(guid.lower(), {})
        result = labels.get(self.input_key(guid, input_name))
        if result:
            return result
        if input_name.rstrip().endswith(('+', '-')):
            base = labels.get(normalized(input_name.rstrip()[:-1]))
            if base:
                return base + ' ' + input_name.rstrip()[-1]
        return ''

    def set(self, guid, input_name, label):
        label = label.strip()
        if len(label) > 120:
            raise ValueError('Use a name of 120 characters or fewer.')
        labels = self.devices.setdefault(guid.lower(), {})
        if label:
            labels[self.input_key(guid, input_name)] = label
        else:
            labels.pop(self.input_key(guid, input_name), None)
        self.save()

    def save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            staging = self.path.with_suffix('.tmp')
            staging.write_text(json.dumps(self.devices, indent=2), encoding='utf-8')
            staging.replace(self.path)
