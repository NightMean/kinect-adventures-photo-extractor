"""Batch CLI with an exclusive, failure-cleaned ZIP destination."""

import argparse
from importlib import metadata, resources
import json
from pathlib import Path
import re
import sys
import zipfile

from .jpeg import MAX_FILE_BYTES, scan_jpegs

TEXT = json.loads(resources.files('kinect_photos').joinpath('messages.json').read_text('utf-8'))


def _inputs(paths: list[str], recursive: bool) -> list[Path]:
    found: dict[Path, None] = {}
    for value in paths:
        path = Path(value).resolve()
        if path.is_dir():
            if not recursive:
                raise ValueError(TEXT['input_directory'].format(path=path))
            for item in sorted(path.rglob('*')):
                if item.is_file() and not item.is_symlink():
                    found[item.resolve()] = None
        elif path.is_file():
            found[path] = None
        else:
            raise ValueError(TEXT['input_missing'].format(path=path))
    if not found:
        raise ValueError(TEXT['no_inputs'])
    return list(found)


def _stem(name: str) -> str:
    # ASCII, bounded, cross-platform names prevent traversal and ZIP ambiguity.
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:100] or 'photo'


def extract(paths: list[Path], output: Path) -> dict:
    """Write a new ZIP and a path-redacted manifest; preserve all source bytes."""
    report = {'schema_version': 1, 'photos': 0, 'files': [], 'skipped': 0, 'failed': 0}
    with output.open('xb') as stream:
        completed = False
        try:
            with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                for index, path in enumerate(paths, 1):
                    record = {'source': path.name, 'photos': [], 'rejected_candidates': 0}
                    try:
                        with path.open('rb') as source:
                            data = source.read(MAX_FILE_BYTES + 1)
                        result = scan_jpegs(data)
                    except OSError:
                        record['error'] = 'read_error'
                    except ValueError as exc:
                        record['error'] = str(exc)
                    else:
                        record['rejected_candidates'] = result.rejected_candidates
                        for number, photo in enumerate(result.photos, 1):
                            name = f'{index:04d}_{_stem(path.name)}_{number:03d}.jpg'
                            archive.writestr(name, data[photo.offset:photo.end])
                            record['photos'].append({'name': name, 'offset': photo.offset,
                                                     'length': photo.end - photo.offset,
                                                     'width': photo.width, 'height': photo.height})
                            report['photos'] += 1
                        if not result.photos:
                            record['notice'] = 'no_photos'
                            report['skipped'] += 1
                    if 'error' in record:
                        report['failed'] += 1
                    report['files'].append(record)
                archive.writestr('manifest.json', json.dumps(report, ensure_ascii=True, indent=2))
            completed = True
        finally:
            if not completed:
                stream.close()
                output.unlink(missing_ok=True)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=TEXT['description'])
    parser.add_argument('inputs', nargs='+', help=TEXT['inputs_help'])
    parser.add_argument('-o', '--output', required=True, type=Path, help=TEXT['output_help'])
    parser.add_argument('-r', '--recursive', action='store_true', help=TEXT['recursive_help'])
    parser.add_argument('-V', '--version', action='version',
                        version=metadata.version('kinect-adventures-photo-extractor'))
    args = parser.parse_args(argv)
    try:
        paths = _inputs(args.inputs, args.recursive)
        output = args.output.resolve()
        if output in paths:
            raise ValueError(TEXT['output_in_inputs'])
        report = extract(paths, output)
    except FileExistsError:
        print(TEXT['error'].format(detail=TEXT['output_exists'].format(path=args.output)), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(TEXT['error'].format(detail=exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(TEXT['cancelled'], file=sys.stderr)
        return 130
    print(TEXT['summary'].format(photos=report['photos'], files=len(paths),
                               skipped=report['skipped'], failed=report['failed'], path=output))
    if report['skipped']:
        print(TEXT['no_photos'], file=sys.stderr)
    for record in report['files']:
        if 'error' in record:
            print(f"{record['source']}: {TEXT[record['error']]}", file=sys.stderr)
    return 2 if report['failed'] else (0 if report['photos'] else 1)
