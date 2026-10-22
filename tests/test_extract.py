import base64
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from kinect_photos.cli import _inputs, extract, main
from kinect_photos.jpeg import scan_jpegs

CASES = json.loads((Path(__file__).parent / 'fixtures.json').read_text('utf-8'))


class JpegTests(unittest.TestCase):
    def test_shared_vectors(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                data = base64.b64decode(case['data'])
                result = scan_jpegs(data)
                actual = [[p.offset, p.end, p.width, p.height] for p in result.photos]
                self.assertEqual(actual, case['photos'])
                self.assertEqual(result.rejected_candidates, case['rejected'])

    def test_every_truncation(self):
        data = base64.b64decode(CASES[0]['data'])
        for end in range(len(data)):
            self.assertFalse(scan_jpegs(data[:end]).photos, end)

    def test_bounded_random_input(self):
        rng = random.Random(20261022)
        for _ in range(300):
            data = rng.randbytes(rng.randrange(2048))
            result = scan_jpegs(data)
            self.assertFalse(result.photos)

    def test_size_limit(self):
        with patch('kinect_photos.jpeg.MAX_FILE_BYTES', 1):
            with self.assertRaisesRegex(ValueError, 'file_too_large'):
                scan_jpegs(b'ab')


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'PM9_test'
        self.data = base64.b64decode(CASES[0]['data'])
        self.source.write_bytes(b'container' + self.data + b'padding')
        self.output = self.root / 'out.zip'

    def test_zip_bytes_manifest_and_duplicate_names(self):
        other = self.root / 'sub' / self.source.name
        other.parent.mkdir()
        other.write_bytes(self.source.read_bytes())
        report = extract([self.source, other], self.output)
        self.assertEqual(report['photos'], 2)
        with zipfile.ZipFile(self.output) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(set(archive.namelist())), 3)
            for name in archive.namelist():
                if name.endswith('.jpg'):
                    self.assertEqual(archive.read(name), self.data)
            text = archive.read('manifest.json').decode()
            self.assertNotIn(str(self.root), text)
            self.assertEqual(json.loads(text), report)
        self.assertTrue(self.source.read_bytes().startswith(b'container'))

    def test_existing_output_and_source_are_preserved(self):
        self.output.write_bytes(b'keep me')
        with self.assertRaises(FileExistsError):
            extract([self.source], self.output)
        self.assertEqual(self.output.read_bytes(), b'keep me')
        self.assertEqual(main([str(self.source), '-o', str(self.source)]), 1)

    def test_partial_failure_and_skip_are_reported(self):
        empty = self.root / 'GameProgress'
        empty.write_bytes(b'not a photo')
        report = extract([self.source, empty, self.root / 'missing'], self.output)
        self.assertEqual((report['photos'], report['skipped'], report['failed']), (1, 1, 1))
        self.assertEqual(report['files'][2]['error'], 'read_error')

    def test_cancelled_write_is_removed(self):
        with patch('zipfile.ZipFile.writestr', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                extract([self.source], self.output)
        self.assertFalse(self.output.exists())

    def test_recursive_inputs_and_duplicates(self):
        self.assertEqual(_inputs([str(self.source), str(self.source)], False), [self.source])
        with self.assertRaisesRegex(ValueError, 'requires --recursive'):
            _inputs([str(self.root)], False)
        self.assertEqual(_inputs([str(self.root)], True), [self.source])


if __name__ == '__main__':
    unittest.main()
