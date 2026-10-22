"""Immutable photo inventory for browsing and exporting a validated selection."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Callable, Literal

from .jpeg import MAX_FILE_BYTES, Photo, scan_jpegs
from .recovery import HEADER_SIZE, OperationCancelled, discover, is_photo_candidate

MAX_CATALOG_PHOTOS = 20_000
DATE_PATTERN = re.compile(r'^PM9_\d+_(\d{4})_(\d{1,2})_(\d{1,2})_(\d{1,2})_(\d{1,2})_(\d{1,2})_(\d{1,3})(?:\.[^.]+)?$', re.IGNORECASE)
DateSource = Literal['filename', 'modified', 'unknown']


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    relative: str
    digest: str


@dataclass(frozen=True)
class PhotoEntry:
    source: SourceSnapshot
    number: int
    image: Photo
    date: datetime | None
    date_source: DateSource


@dataclass(frozen=True)
class CatalogIssue:
    source: str
    code: str
    rejected_candidates: int = 0


@dataclass(frozen=True)
class PhotoCatalog:
    root: Path
    photos: tuple[PhotoEntry, ...]
    inspected: int
    skipped: int
    issues: tuple[CatalogIssue, ...]
    discovery_issues: tuple[str, ...]
    discovery_issue_count: int


@dataclass(frozen=True)
class ScanProgress:
    phase: Literal['discover', 'validate']
    current: int
    total: int
    photos: int


def photo_date(name: str, modified: float) -> tuple[datetime | None, DateSource]:
    match = DATE_PATTERN.fullmatch(name)
    if match:
        try:
            year, month, day, hour, minute, second, millisecond = map(int, match.groups())
            return datetime(year, month, day, hour, minute, second, millisecond * 1000), 'filename'
        except ValueError:
            pass  # Invalid console dates fall back to the explicitly labelled file date.
    try:
        return datetime.fromtimestamp(modified, timezone.utc).astimezone(), 'modified'
    except (ValueError, OverflowError, OSError):
        return None, 'unknown'


def scan_folder(input_folder: Path, output_folder: Path | None = None, *,
                cancelled: Callable[[], bool] = lambda: False,
                progress: Callable[[ScanProgress], None] | None = None) -> PhotoCatalog:
    root = input_folder.resolve()
    if not root.is_dir():
        raise ValueError('input_folder_missing')
    excluded = output_folder.resolve() if output_folder else None
    if excluded == root:
        raise ValueError('same_folders')
    def discovery_progress(inspected, candidates):
        if progress:
            progress(ScanProgress('discover', inspected, 0, 0))
    found = discover(root, excluded, cancelled=cancelled, progress=discovery_progress)
    photos: list[PhotoEntry] = []
    issues: list[CatalogIssue] = []
    skipped = 0
    for current, path in enumerate(found.files, 1):
        if cancelled():
            raise OperationCancelled()
        relative = path.relative_to(root).as_posix()
        try:
            with path.open('rb') as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
                modified = path.stat().st_mtime
            if not is_photo_candidate(path.name, data[:HEADER_SIZE]):
                raise ValueError('source_changed')
            result = scan_jpegs(data)
            snapshot = SourceSnapshot(path, relative, hashlib.sha256(data).hexdigest())
            date, origin = photo_date(path.name, modified)
            for number, image in enumerate(result.photos, 1):
                if len(photos) >= MAX_CATALOG_PHOTOS:
                    raise ValueError('catalog_photo_limit')
                photos.append(PhotoEntry(snapshot, number, image, date, origin))
            if not result.photos:
                skipped += 1
            if result.rejected_candidates:
                issues.append(CatalogIssue(relative, 'rejected_jpeg', result.rejected_candidates))
        except OSError:
            issues.append(CatalogIssue(relative, 'read_error'))
        except ValueError as exc:
            if str(exc) == 'catalog_photo_limit':
                raise
            issues.append(CatalogIssue(relative, str(exc)))
        if progress:
            progress(ScanProgress('validate', current, len(found.files), len(photos)))
    if cancelled():
        raise OperationCancelled()
    return PhotoCatalog(root, tuple(photos), found.inspected, skipped, tuple(issues),
                        found.issues, found.issue_count)


def read_source(snapshot: SourceSnapshot) -> bytes:
    with snapshot.path.open('rb') as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != snapshot.digest:
        raise ValueError('source_changed')
    return data


def read_photo(entry: PhotoEntry) -> bytes:
    data = read_source(entry.source)
    if not 0 <= entry.image.offset < entry.image.end <= len(data):
        raise ValueError('source_changed')
    return data[entry.image.offset:entry.image.end]


class PhotoSelection:
    """Checkbox state and Shift range semantics independent of native widgets."""
    def __init__(self, count: int):
        self.count = count
        self.checked = set(range(count))
        self.anchor: int | None = None

    def all(self, checked: bool) -> None:
        self.checked = set(range(self.count)) if checked else set()
        self.anchor = None

    def toggle(self, index: int, checked: bool, shift: bool = False) -> range:
        if not 0 <= index < self.count:
            raise ValueError('invalid_selection')
        start = self.anchor if shift and self.anchor is not None else index
        affected = range(min(start, index), max(start, index) + 1)
        if checked:
            self.checked.update(affected)
        else:
            self.checked.difference_update(affected)
        if not shift or self.anchor is None:
            self.anchor = index
        return affected
