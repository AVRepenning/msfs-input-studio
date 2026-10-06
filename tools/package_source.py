"""Create a reproducible source bundle alongside the standalone executable."""
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    dist = root / 'dist'
    dist.mkdir(exist_ok=True)
    files = [root / name for name in ('msfs_input_studio.py', 'build.bat', 'requirements.txt',
             'README.md', 'FEATURE_MATRIX.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', '.gitignore')]
    for name in ('msfs_config', 'tests', 'tools', 'data', 'research/community-profiles/profiles'):
        files.extend(path for path in (root / name).rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    target = dist / 'MSFSInputStudio-source.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(root))
    print(f'Source archive: {len(files)} files, {target.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
