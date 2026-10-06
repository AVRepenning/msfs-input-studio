"""Read controller XML copies from local Store saves; never modify cloud storage."""
from pathlib import Path
import os
import xml.etree.ElementTree as ET

from .profiles import Profile


def profile_folders():
    packages = Path(os.environ.get('LOCALAPPDATA', '.')) / 'Packages'
    return [folder for folder in packages.glob('Microsoft.Limitless_*/SystemAppData/wgs') if folder.is_dir()]


def is_managed_save(path, folders=None):
    target = Path(path).resolve()
    return any(target.is_relative_to(Path(folder).resolve()) for folder in (profile_folders() if folders is None else folders))


def scan_profiles(folders=None, cancel_event=None):
    found = []
    seen = set()
    for folder in profile_folders() if folders is None else folders:
        for path in Path(folder).glob('*/*/*'):
            if cancel_event is not None and cancel_event.is_set():
                return found
            if not path.is_file() or path.name.startswith('container') or path in seen:
                continue
            seen.add(path)
            if len(seen) > 1500:
                break
            try:
                if not 20 < path.stat().st_size <= 20_000_000:
                    continue
                with path.open('rb') as stream:
                    header = stream.read(8192)
                if b'<Device' not in header or b'<FriendlyName' not in header:
                    continue
                profile = Profile.load(path)
                found.append({'path': path, 'profile': profile, 'name': profile.name,
                              'device': profile.device.get('DeviceName', ''), 'category': profile.category,
                              'bindings': profile.bound_slot_count()})
            except (OSError, ValueError, ET.ParseError):
                continue
    return sorted(found, key=lambda row: (row['device'].casefold(), row['category'], row['name'].casefold()))
