import base64
from datetime import datetime
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import random
import struct
import tempfile
import unittest

from kinect_photos.capture_metadata import embed_capture_date
from kinect_photos.catalog import scan_folder
from kinect_photos.recovery import recover_selection

JPEG = base64.b64decode(json.loads((Path(__file__).parent / 'fixtures.json').read_text())[0]['data'])
DATE = datetime(2010, 12, 28, 18, 22, 20, 510000)


def exif_segment(tiff):
    payload = b'Exif\0\0' + tiff
    return b'\xff\xe1' + (len(payload) + 2).to_bytes(2, 'big') + payload


def exif_range(jpeg):
    offset = 2
    while jpeg[offset:offset + 2] != b'\xff\xda':
        length = int.from_bytes(jpeg[offset + 2:offset + 4], 'big')
        end = offset + 2 + length
        if jpeg[offset:offset + 2] == b'\xff\xe1' and jpeg[offset + 4:offset + 10] == b'Exif\0\0':
            return offset, end, jpeg[offset + 10:end]
        offset = end
    raise AssertionError('No EXIF segment')


def existing_tiff(endian):
    def directory(entries, next_ifd=0):
        return struct.pack(endian + 'H', len(entries)) + b''.join(entries) + struct.pack(endian + 'I', next_ifd)
    def entry(tag, kind, count, value):
        return struct.pack(endian + 'HHI', tag, kind, count) + value
    pointer = lambda offset: struct.pack(endian + 'I', offset)
    header = (b'II' if endian == '<' else b'MM') + struct.pack(endian + 'HI', 42, 8)
    root = directory([entry(0x0112, 3, 1, struct.pack(endian + 'H', 6) + b'\0\0'),
                      entry(0x8769, 4, 1, pointer(50)), entry(0x8825, 4, 1, pointer(68))], 86)
    exif = directory([entry(0x927c, 7, 8, pointer(92))])
    gps = directory([entry(0, 1, 4, bytes((2, 3, 0, 0)))])
    return header + root + exif + gps + directory([]) + b'NOTEraw!'


class CaptureMetadataTests(unittest.TestCase):
    def test_capture_date_preserves_jpeg_bytes_and_is_idempotent(self):
        output = embed_capture_date(JPEG, DATE)
        start, end, tiff = exif_range(output)
        self.assertEqual(output[:start] + output[end:], JPEG)
        self.assertIn(b'2010:12:28 18:22:20\0', tiff)
        self.assertIn(b'510\0', tiff)
        self.assertEqual(embed_capture_date(output, DATE), output)

    def test_existing_opaque_metadata_gps_orientation_and_thumbnail_offsets_survive(self):
        for endian in ('<', '>'):
            original = existing_tiff(endian)
            source = JPEG[:2] + exif_segment(original) + JPEG[2:]
            output = embed_capture_date(source, DATE)
            _, _, rewritten = exif_range(output)
            self.assertEqual(rewritten[:4], original[:4])
            self.assertEqual(rewritten[8:len(original)], original[8:])
            root = struct.unpack_from(endian + 'I', rewritten, 4)[0]
            count = struct.unpack_from(endian + 'H', rewritten, root)[0]
            self.assertEqual(struct.unpack_from(endian + 'I', rewritten, root + 2 + count * 12)[0], 86)
            self.assertEqual(embed_capture_date(output, DATE), output)

    def test_malformed_duplicate_and_oversized_metadata_fail_explicitly(self):
        empty = b'II\x2a\0\x08\0\0\0\0\0\0\0\0\0'
        for tiff in (b'', b'bad', empty[:10], b'II\x2a\0\xff\xff\xff\xff',
                     empty[:8] + b'\xff\xff' + b'\0' * 4):
            with self.subTest(tiff=tiff), self.assertRaisesRegex(ValueError, 'metadata_invalid'):
                embed_capture_date(JPEG[:2] + exif_segment(tiff) + JPEG[2:], DATE)
        duplicated = JPEG[:2] + exif_segment(empty) * 2 + JPEG[2:]
        with self.assertRaisesRegex(ValueError, 'metadata_invalid'):
            embed_capture_date(duplicated, DATE)
        large = empty + b'\0' * (65527 - len(empty))
        with self.assertRaisesRegex(ValueError, 'metadata_too_large'):
            embed_capture_date(JPEG[:2] + exif_segment(large) + JPEG[2:], DATE)
        rng = random.Random(429)
        for _ in range(100):
            damaged = rng.randbytes(rng.randrange(100))
            with self.assertRaises(ValueError):
                embed_capture_date(JPEG[:2] + exif_segment(damaged) + JPEG[2:], DATE)

    def test_enabled_disabled_fallback_and_rerun_export_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'input'
            source.mkdir()
            dated = source / 'PM9_0_2010_12_28_18_22_20_510'
            dated.write_bytes(JPEG)
            (source / 'PM9_no_date').write_bytes(JPEG)
            catalog = scan_folder(source)
            report, path = recover_selection(catalog, (0, 1), root / 'output', embed_dates=True)
            self.assertEqual((report.recovered, report.failed), (2, 0))
            records = {record.source: record.photos[0] for record in report.files}
            self.assertTrue(records[dated.name]['metadata_embedded'])
            self.assertEqual(records[dated.name]['capture_date'], '2010-12-28T18:22:20.510')
            self.assertFalse(records['PM9_no_date']['metadata_embedded'])
            self.assertEqual((path.parent / records['PM9_no_date']['name']).read_bytes(), JPEG)
            again, _ = recover_selection(catalog, (0, 1), root / 'output', embed_dates=True)
            self.assertEqual((again.recovered, again.existing), (0, 2))
            plain, _ = recover_selection(catalog, (0,), root / 'plain', embed_dates=False)
            self.assertEqual((root / 'plain' / plain.files[0].photos[0]['name']).read_bytes(), JPEG)
            self.assertEqual(dated.read_bytes(), JPEG)

    def test_failed_metadata_never_publishes_a_partial_photo_and_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'input'
            source.mkdir()
            damaged = JPEG[:2] + exif_segment(b'invalid') + JPEG[2:]
            (source / 'PM9_0_2010_12_28_18_22_20_510').write_bytes(damaged)
            catalog = scan_folder(source)
            report, _ = recover_selection(catalog, (0,), root / 'output', embed_dates=True)
            self.assertEqual((report.recovered, report.failed), (0, 1))
            self.assertEqual(report.files[0].error, 'metadata_invalid')
            self.assertFalse(list((root / 'output').glob('*.jpg')))
            self.assertFalse(list((root / 'output').glob('*.tmp')))
            plain, _ = recover_selection(catalog, (0,), root / 'output', embed_dates=False)
            self.assertEqual(plain.recovered, 1)
            self.assertEqual((root / 'output' / plain.files[0].photos[0]['name']).read_bytes(), damaged)

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow verification dependency required')
    def test_independent_exif_reader_and_decoded_pixels(self):
        from PIL import Image
        for tiff in (None, existing_tiff('<'), existing_tiff('>')):
            source = JPEG if tiff is None else JPEG[:2] + exif_segment(tiff) + JPEG[2:]
            output = embed_capture_date(source, DATE)
            with Image.open(BytesIO(source)) as before, Image.open(BytesIO(output)) as after:
                self.assertEqual(before.tobytes(), after.tobytes())
                exif = after.getexif()
                dates = exif.get_ifd(0x8769)
                self.assertEqual(exif[0x0132], '2010:12:28 18:22:20')
                self.assertEqual(dates[0x9003], '2010:12:28 18:22:20')
                self.assertEqual(dates[0x9004], '2010:12:28 18:22:20')
                for tag in (0x9290, 0x9291, 0x9292):
                    self.assertEqual(dates[tag], '510')
                if tiff:
                    self.assertEqual(exif[0x0112], 6)
                    self.assertEqual(dates[0x927c], b'NOTEraw!')
                    self.assertEqual(exif.get_ifd(0x8825)[0], b'\x02\x03\0\0')
