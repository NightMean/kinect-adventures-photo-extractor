"""Build the standalone Windows GUI without requiring an environment for users."""

import argparse
from importlib.metadata import version
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-V', '--version', action='version',
                        version=version('kinect-adventures-photo-extractor'))
    parser.parse_args()
    if os.name != 'nt':
        parser.error('Build the Windows executable on Windows.')
    root = Path(__file__).resolve().parent.parent
    logs = root / 'build'
    logs.mkdir(exist_ok=True)
    log = logs / 'windows-build.log'
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm',
               '--distpath', str(root / 'build' / 'windows-dist'),
               '--workpath', str(root / 'build' / 'pyinstaller'), str(root / 'KinectPhotos.spec')]
    try:
        with log.open('w', encoding='utf-8') as output:
            result = subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                    timeout=600, check=False)
    except subprocess.TimeoutExpired:
        print(f'Build exceeded 10 minutes. Log: {log}', file=sys.stderr)
        return 1
    if result.returncode:
        print(f'Build failed ({result.returncode}). Log: {log}', file=sys.stderr)
        return result.returncode
    destination = root / 'dist' / 'desktop' / 'KinectPhotos.exe'
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(root / 'build' / 'windows-dist' / 'KinectPhotos.exe', destination)
    except OSError as exc:
        print(f'Cannot replace the executable. Close the app and retry. {exc}', file=sys.stderr)
        return 1
    print(f"Built {root / 'dist' / 'desktop' / 'KinectPhotos.exe'}")
    print(f'Build log: {log}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
