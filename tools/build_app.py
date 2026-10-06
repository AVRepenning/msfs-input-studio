"""Build each version into its own folder so an open earlier app stays usable."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from msfs_config import __version__


def main():
    target = root / 'dist' / ('v' + __version__)
    work = Path(os.environ.get('LOCALAPPDATA', '.')) / 'MSFSInputStudio/build' / __version__
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--workpath', str(work), '--distpath', str(target), '--onefile', '--windowed',
               '--name', 'MSFSInputStudio', '--add-data', 'data;data']
    for name in ('README.md', 'FEATURE_MATRIX.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        command.extend(['--add-data', name + ';.'])
    subprocess.run(command + ['msfs_input_studio.py'], cwd=root, check=True)
    print('Built ' + str(target / 'MSFSInputStudio.exe'))


if __name__ == '__main__':
    main()
