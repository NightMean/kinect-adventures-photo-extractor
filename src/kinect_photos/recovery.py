"""Discover Kinect photo saves below one root and publish lossless JPG files."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable

from .jpeg import MAX_FILE_BYTES, scan_jpegs

TITLE_ID = bytes.fromhex('4d5308ed')
HEADER_SIZE = 0x364
MAX_CANDIDATES = 20_000
MAX_ISSUES = 200


@dataclass(frozen=True)
class Discovery:
    files: tuple[Path, ...]
    inspected: int
    issues: tuple[str, ...]
    issue_count: int


@dataclass
class FileResult:
    source: str  # Relative to the selected root, never an absolute private path.
    photos: list[dict] = field(default_factory=list)
    rejected_candidates: int = 0
    error: str | None = None


@dataclass
class RecoveryReport:
    schema_version: int = 1
    version: str = ''
    started_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    inspected: int = 0
    recovered: int = 0
    existing: int = 0
    skipped: int = 0
    failed: int = 0
    discovery_issue_count: int = 0
    discovery_issues: tuple[str, ...] = ()
    files: list[FileResult] = field(default_factory=list)


def _candidate(name: str, header: bytes) -> bool:
    lower = name.casefold()
    if lower == 'gameprogress' or lower.startswith('souvenirrecording'):
        return False
    return lower.startswith('pm9_') or (
        header[:4] in (b'CON ', b'LIVE', b'PIRS')
        and header[0x360:0x364] == TITLE_ID
    )


def _reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    )


def discover(root: Path, output: Path) -> Discovery:
    """Inspect bounded headers; skip links/junctions and the selected output tree."""
    files: list[Path] = []
    inspected = issue_count = 0
    issues: list[str] = []

    def issue(path: Path) -> None:
        nonlocal issue_count
        issue_count += 1
        if len(issues) < MAX_ISSUES:
            issues.append(path.relative_to(root).as_posix())

    def walk_error(exc: OSError) -> None:
        issue(Path(exc.filename) if exc.filename else root)

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        parent = Path(directory)
        kept = []
        for name in sorted(dirs):
            path = parent / name
            try:
                if path != output and not _reparse(path):
                    kept.append(name)
            except OSError:
                issue(path)
        dirs[:] = kept
        for name in sorted(names):
            path = parent / name
            try:
                if _reparse(path) or not path.is_file():
                    continue
                inspected += 1
                with path.open('rb') as stream:
                    header = stream.read(HEADER_SIZE)
                if _candidate(name, header):
                    if len(files) >= MAX_CANDIDATES:
                        raise ValueError('candidate_limit')
                    files.append(path)
            except OSError:
                issue(path)
    return Discovery(tuple(files), inspected, tuple(issues), issue_count)


def _safe_stem(name: str) -> str:
    stem = re.sub(r'[^a-zA-Z0-9_-]', '_', name)[:100] or 'photo'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', stem, re.IGNORECASE):
        stem = 'photo_' + stem
    return stem


def _publish(output: Path, stem: str, extension: str, data: bytes) -> tuple[str, bool]:
    """Publish a fully written file exclusively; never replace an existing file.

    Windows rename is exclusive. POSIX rename overwrites, so POSIX uses an
    exclusive hard link. Force-quit may leave .kinect-*.tmp, never a partial JPG.
    """
    temp: Path | None = None
    try:
        for index in range(1, 10_001):
            suffix = '' if index == 1 else f'_{index}'
            path = output / f'{stem}{suffix}{extension}'
            try:
                if path.is_file() and not _reparse(path):
                    with path.open('rb') as existing:
                        if existing.read(len(data) + 1) == data:
                            return path.name, False
            except OSError:
                pass  # An unreadable collision is preserved; publication chooses another name.
            if temp is None:
                with tempfile.NamedTemporaryFile(prefix='.kinect-', suffix='.tmp', dir=output, delete=False) as stream:
                    temp = Path(stream.name)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            try:
                if os.name == 'nt':
                    os.rename(temp, path)
                else:
                    os.link(temp, path)
                return path.name, True
            except FileExistsError:
                continue
        raise OSError('output_name_limit')
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def recover_folder(input_folder: Path, output_folder: Path, *, version: str = '',
                   progress: Callable[[int, int], None] | None = None) -> tuple[RecoveryReport, Path]:
    """Recursively discover photos, publish JPGs, and save a bounded local report."""
    root, output = input_folder.resolve(), output_folder.resolve()
    if not root.is_dir():
        raise ValueError('input_folder_missing')
    if root == output:
        raise ValueError('same_folders')
    output.mkdir(parents=True, exist_ok=True)
    found = discover(root, output)
    report = RecoveryReport(version=version, inspected=found.inspected,
                            discovery_issues=found.issues, discovery_issue_count=found.issue_count)
    for index, source in enumerate(found.files, 1):
        record = FileResult(source.relative_to(root).as_posix())
        try:
            with source.open('rb') as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if not _candidate(source.name, data[:HEADER_SIZE]):
                raise ValueError('source_changed')
            result = scan_jpegs(data)
            record.rejected_candidates = result.rejected_candidates
            for number, photo in enumerate(result.photos, 1):
                stem = _safe_stem(source.name) + (f'_image_{number}' if number > 1 else '')
                name, created = _publish(output, stem, '.jpg', data[photo.offset:photo.end])
                record.photos.append({'name': name, 'offset': photo.offset,
                                      'length': photo.end - photo.offset,
                                      'width': photo.width, 'height': photo.height,
                                      'created': created})
                if created:
                    report.recovered += 1
                else:
                    report.existing += 1
            if not result.photos:
                report.skipped += 1
        except ValueError as exc:
            record.error = str(exc)
        except OSError:
            record.error = 'file_io_error'
        if record.error:
            report.failed += 1
        report.files.append(record)
        if progress is not None:
            progress(index, len(found.files))
    encoded = json.dumps(asdict(report), ensure_ascii=True, indent=2).encode('utf-8')
    name, _ = _publish(output, 'recovery-report', '.json', encoded)
    return report, output / name
