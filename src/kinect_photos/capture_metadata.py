"""Add filename capture dates to EXIF without re-encoding JPEG image data."""

from datetime import datetime
import struct

EXIF_PREFIX = b'Exif\0\0'
EXIF_IFD = 0x8769
DATE_TIME = 0x0132
ORIGINAL_TIME = 0x9003
DIGITIZED_TIME = 0x9004
SUBSECOND_TAGS = (0x9290, 0x9291, 0x9292)
OFFSET_TAGS = (0x9010, 0x9011, 0x9012)
MAX_APP_PAYLOAD = 65_533


def _header(data: bytes) -> tuple[int, tuple[int, int, bytes] | None]:
    if data[:2] != b'\xff\xd8':
        raise ValueError('metadata_invalid')
    position, insertion, existing = 2, 2, None
    while position < len(data):
        start = position
        if data[position] != 0xff:
            break
        while position < len(data) and data[position] == 0xff:
            position += 1
        if position >= len(data):
            break
        marker = data[position]
        position += 1
        if marker == 0xda:  # Stop at the first scan: image/scan bytes stay untouched.
            return insertion, existing
        if marker == 0x01 or 0xd0 <= marker <= 0xd7:
            continue
        if marker in (0, 0xd8, 0xd9) or position + 2 > len(data):
            break
        length = int.from_bytes(data[position:position + 2], 'big')
        end = position + length
        if length < 2 or end > len(data):
            break
        payload = data[position + 2:end]
        if marker == 0xe0 and start == 2:
            insertion = end  # Keep a leading JFIF APP0 first.
        if marker == 0xe1 and payload.startswith(EXIF_PREFIX):
            if existing is not None:
                raise ValueError('metadata_invalid')
            existing = start, end, payload[len(EXIF_PREFIX):]
        position = end
    raise ValueError('metadata_invalid')


def _ifd(data: bytes, offset: int, endian: str) -> tuple[dict[int, bytes], int]:
    if offset < 8 or offset + 2 > len(data):
        raise ValueError('metadata_invalid')
    count = struct.unpack_from(endian + 'H', data, offset)[0]
    end = offset + 2 + count * 12
    if end + 4 > len(data):
        raise ValueError('metadata_invalid')
    entries = {}
    for position in range(offset + 2, end, 12):
        tag = struct.unpack_from(endian + 'H', data, position)[0]
        if tag in entries:
            raise ValueError('metadata_invalid')
        entries[tag] = data[position:position + 12]
    return entries, struct.unpack_from(endian + 'I', data, end)[0]


def _ascii_value(data: bytes, entry: bytes | None, endian: str) -> bytes | None:
    if entry is None:
        return None
    _, kind, count = struct.unpack_from(endian + 'HHI', entry)
    if kind != 2:
        return None
    if count <= 4:
        return entry[8:8 + count]
    offset = struct.unpack_from(endian + 'I', entry, 8)[0]
    if offset < 8 or offset + count > len(data):
        raise ValueError('metadata_invalid')
    return data[offset:offset + count]


def _append_ifd(data: bytearray, entries: dict[int, bytes], next_ifd: int, endian: str) -> int:
    if len(data) % 2:
        data.append(0)
    offset = len(data)
    data.extend(struct.pack(endian + 'H', len(entries)))
    for tag in sorted(entries):
        data.extend(entries[tag])
    data.extend(struct.pack(endian + 'I', next_ifd))
    return offset


def embed_capture_date(jpeg: bytes, date: datetime) -> bytes:
    """Set EXIF capture/digitization dates to the console's unzoned filename clock.

    Existing TIFF data and pointers remain at their original offsets. Append new
    directories instead of reserializing old metadata: EXIF serializers can drop
    thumbnail IFDs or relocate opaque MakerNote data. Only the root pointer changes.
    """
    if date.tzinfo is not None:
        raise ValueError('metadata_invalid')
    insertion, existing = _header(jpeg)
    original = existing[2] if existing else b'II\x2a\0\x08\0\0\0\0\0\0\0\0\0'
    if len(original) < 8 or original[:2] not in (b'II', b'MM'):
        raise ValueError('metadata_invalid')
    endian = '<' if original[:2] == b'II' else '>'
    if struct.unpack_from(endian + 'H', original, 2)[0] != 42:
        raise ValueError('metadata_invalid')
    root, thumbnail = _ifd(original, struct.unpack_from(endian + 'I', original, 4)[0], endian)
    exif, exif_next = {}, 0
    if EXIF_IFD in root:
        pointer = root[EXIF_IFD]
        if struct.unpack_from(endian + 'HI', pointer, 2) != (4, 1):
            raise ValueError('metadata_invalid')
        exif, exif_next = _ifd(original, struct.unpack_from(endian + 'I', pointer, 8)[0], endian)
    stamp = (f'{date.year:04d}:{date.month:02d}:{date.day:02d} '
             f'{date.hour:02d}:{date.minute:02d}:{date.second:02d}').encode('ascii') + b'\0'
    fraction = f'{date.microsecond // 1000:03d}'.encode('ascii') + b'\0'
    desired = {ORIGINAL_TIME: stamp, DIGITIZED_TIME: stamp,
               **dict.fromkeys(SUBSECOND_TAGS, fraction)}
    if (_ascii_value(original, root.get(DATE_TIME), endian) == stamp and
            all(_ascii_value(original, exif.get(tag), endian) == value for tag, value in desired.items()) and
            not any(tag in exif for tag in OFFSET_TAGS)):
        return jpeg
    data = bytearray(original)

    def ascii_entry(tag: int, value: bytes) -> bytes:
        if len(value) <= 4:
            encoded = value.ljust(4, b'\0')
        else:
            if len(data) % 2:
                data.append(0)
            encoded = struct.pack(endian + 'I', len(data))
            data.extend(value)
        return struct.pack(endian + 'HHI', tag, 2, len(value)) + encoded

    for tag, value in desired.items():
        exif[tag] = ascii_entry(tag, value)
    for tag in OFFSET_TAGS:
        exif.pop(tag, None)  # Filename dates do not supply a trustworthy UTC offset.
    exif.setdefault(0x9000, struct.pack(endian + 'HHI', 0x9000, 7, 4) + b'0232')
    exif_offset = _append_ifd(data, exif, exif_next, endian)
    root[DATE_TIME] = ascii_entry(DATE_TIME, stamp)
    root[EXIF_IFD] = struct.pack(endian + 'HHII', EXIF_IFD, 4, 1, exif_offset)
    root_offset = _append_ifd(data, root, thumbnail, endian)
    struct.pack_into(endian + 'I', data, 4, root_offset)
    payload = EXIF_PREFIX + bytes(data)
    if len(payload) > MAX_APP_PAYLOAD:
        raise ValueError('metadata_too_large')
    segment = b'\xff\xe1' + (len(payload) + 2).to_bytes(2, 'big') + payload
    start, end = existing[:2] if existing else (insertion, insertion)
    return jpeg[:start] + segment + jpeg[end:]
