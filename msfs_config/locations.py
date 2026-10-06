"""Discover simulator folders from UserCfg.opt; never edit Xbox cloud saves."""
import os
from pathlib import Path
import re


def simulator_locations():
    local = Path(os.environ.get('LOCALAPPDATA', ''))
    roaming = Path(os.environ.get('APPDATA', ''))
    configs = list((local / 'Packages').glob('Microsoft.Limitless_*/LocalCache/UserCfg.opt'))
    configs += [roaming / 'Microsoft Flight Simulator 2024/UserCfg.opt']
    found = []
    for config in configs:
        if not config.is_file():
            continue
        text = config.read_text(encoding='utf-8-sig', errors='replace')
        match = re.search(r'^InstalledPackagesPath\s+"([^"]+)"', text, re.MULTILINE)
        if match:
            packages = Path(match.group(1))
            for name in ('Community2024', 'Community'):
                community = packages / name
                if community.is_dir():
                    found.append({'config': str(config), 'packages': str(packages), 'community': str(community)})
    return found
