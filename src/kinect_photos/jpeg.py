"""Walk JPEG segments; never mistake a marker inside metadata for image end."""

from dataclasses import dataclass

MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_PHOTOS = 10_000
FRAME_MARKERS = frozenset((0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                           0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF))


@dataclass(frozen=True)
class Photo:
    offset: int
    end: int  # Exclusive, including the two-byte JPEG end marker.
    width: int
    height: int


@dataclass(frozen=True)
class ScanResult:
    photos: tuple[Photo, ...]
    rejected_candidates: int


def _read_jpeg(data: bytes, start: int, budget: list[int]) -> Photo | None:
    pos = start + 2
    width = height = 0
    scanned = False
    entropy = False
    while pos < len(data):
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("scan_budget")
        if entropy:
            pos = data.find(b'\xff', pos)
            if pos < 0:
                return None
        if data[pos] != 0xFF:
            return None
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            return None
        marker = data[pos]
        pos += 1
        if entropy and (marker == 0 or 0xD0 <= marker <= 0xD7):
            continue  # Byte stuffing and restart markers belong to scan data.
        entropy = False
        if marker == 0xD9:
            return Photo(start, pos, width, height) if scanned and width and height else None
        if marker in (0, 0xD8) or 0xD0 <= marker <= 0xD7:
            return None
        if marker == 1:
            continue
        if pos + 2 > len(data):
            return None
        length = int.from_bytes(data[pos:pos + 2], 'big')
        if length < 2 or pos + length > len(data):
            return None
        if marker in FRAME_MARKERS:
            if length < 11:
                return None
            components = data[pos + 7]
            if components == 0 or length != 8 + 3 * components:
                return None
            height = int.from_bytes(data[pos + 3:pos + 5], 'big')
            width = int.from_bytes(data[pos + 5:pos + 7], 'big')
            if not width or not height:
                return None
        if marker == 0xDA:
            if length < 8 or not width or not height:
                return None
            components = data[pos + 2]
            if not components or length != 6 + 2 * components:
                return None
            scanned = entropy = True
        pos += length
    return None


def scan_jpegs(data: bytes) -> ScanResult:
    """Find complete contiguous JPEGs. Structural validation is not pixel decoding.

    Malformed candidates are skipped and counted; valid images later in the file
    remain recoverable. Input size, output count and parser work are bounded.
    """
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("file_too_large")
    photos: list[Photo] = []
    rejected = pos = 0
    budget = [max(1024, len(data) * 2)]
    while (start := data.find(b'\xff\xd8\xff', pos)) >= 0:
        photo = _read_jpeg(data, start, budget)
        if photo is None:
            rejected += 1
            pos = start + 2
        else:
            if len(photos) >= MAX_PHOTOS:
                raise ValueError("too_many_photos")
            photos.append(photo)
            pos = photo.end
    return ScanResult(tuple(photos), rejected)
