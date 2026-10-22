# PyInstaller build: version and package resources come from the installed project.
from importlib.metadata import version
import json
from pathlib import Path
import subprocess
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

release = version('kinect-adventures-photo-extractor')
commit = subprocess.run(['git', 'rev-parse', '--short=12', 'HEAD'], cwd=SPECPATH,
                        check=True, capture_output=True, text=True, timeout=10).stdout.strip()
dirty = bool(subprocess.run(['git', 'status', '--porcelain'], cwd=SPECPATH,
                            check=True, capture_output=True, text=True, timeout=10).stdout.strip())
build_info = Path(SPECPATH) / 'build' / 'build-info.json'
build_info.parent.mkdir(exist_ok=True)
build_info.write_text(json.dumps({'commit': commit, 'dirty': dirty}), encoding='utf-8')
numbers = tuple(int(part) for part in release.split('.')) + (0,)
identity = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3f, flags=0,
                      OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileVersion', release), StringStruct('ProductVersion', release),
        StringStruct('ProductName', 'Kinect Adventures Photo Extractor'),
        StringStruct('FileDescription', 'Recover Kinect Adventures photos'),
        StringStruct('Comments', commit + ('-dirty' if dirty else '')),
    ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])],
)
resources = collect_data_files('kinect_photos')
resources += copy_metadata('kinect-adventures-photo-extractor')
resources += copy_metadata('wxPython', recursive=True) + copy_metadata('Pillow', recursive=True)
resources += [(str(Path(SPECPATH) / 'LICENSE'), 'licenses/project')]
resources += [(str(build_info), 'kinect_photos')]
analysis = Analysis(['KinectPhotos.pyw'], datas=resources, hiddenimports=[],
                    hookspath=[], excludes=['numpy'], noarchive=False)
archive = PYZ(analysis.pure)
exe = EXE(archive, analysis.scripts, analysis.binaries, analysis.datas, [],
          name='KinectPhotos', debug=False, strip=False, upx=False,
          console=True, hide_console='hide-early', version=identity,
          icon=str(Path(SPECPATH) / 'src' / 'kinect_photos' / 'assets' / 'app.ico'))
