import base64
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kinect_photos.recovery import HEADER_SIZE, TITLE_ID, _publish, discover, recover_folder

FIXTURES = json.loads((Path(__file__).parent / 'fixtures.json').read_text('utf-8'))
JPEG = base64.b64decode(FIXTURES[0]['data'])


def package(title=TITLE_ID):
    header = bytearray(HEADER_SIZE)
    header[:4] = b'CON '
    header[0x360:0x364] = title
    return bytes(header) + JPEG + b'padding'


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.input = self.root / 'backup'
        self.output = self.root / 'photos'
        self.input.mkdir()

    def write(self, relative, data):
        path = self.input / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_auto_discovery_filters_other_games_and_animations(self):
        first = self.write('Content/profile/4D5308ED/00000001/PM9_one', package())
        renamed = self.write('elsewhere/renamed', package())
        self.write('another-game', package(b'\x12\x34\x56\x78'))
        self.write('plain.jpg', JPEG)
        self.write('SouvenirRecording0', package())
        self.write('GameProgress', package())
        found = discover(self.input, self.output)
        self.assertEqual(set(found.files), {first, renamed})
        self.assertEqual(found.inspected, 6)

    def test_recursive_recovery_exact_bytes_and_report(self):
        source = self.write('deep/nested/PM9_one', package())
        original = source.read_bytes()
        progress = []
        report, path = recover_folder(self.input, self.output, version='test',
                                      progress=lambda current, total: progress.append((current, total)))
        self.assertEqual((report.recovered, report.existing, report.failed), (1, 0, 0))
        self.assertEqual((self.output / 'PM9_one.jpg').read_bytes(), JPEG)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(progress, [(1, 1)])
        self.assertEqual(json.loads(path.read_text()), json.loads(json.dumps(asdict(report))))
        self.assertNotIn(str(self.root), path.read_text())

    def test_reruns_and_colliding_names_preserve_existing_files(self):
        self.write('a/PM9_same', JPEG)
        changed = JPEG[:2] + b'\xff\xfe\x00\x06test' + JPEG[2:]
        self.write('b/PM9_same', changed)
        self.output.mkdir()
        (self.output / 'PM9_same.jpg').write_bytes(b'precious existing file')
        report, _ = recover_folder(self.input, self.output)
        self.assertEqual(report.recovered, 2)
        self.assertEqual((self.output / 'PM9_same.jpg').read_bytes(), b'precious existing file')
        self.assertEqual((self.output / 'PM9_same_2.jpg').read_bytes(), JPEG)
        self.assertEqual((self.output / 'PM9_same_3.jpg').read_bytes(), changed)
        again, _ = recover_folder(self.input, self.output)
        self.assertEqual((again.recovered, again.existing), (0, 2))
        self.assertEqual(len(list(self.output.glob('*.jpg'))), 3)

    def test_output_subfolder_is_excluded_and_equal_folder_is_rejected(self):
        output = self.input / 'recovered'
        output.mkdir()
        (output / 'PM9_old').write_bytes(JPEG)
        self.write('PM9_new', JPEG)
        report, _ = recover_folder(self.input, output)
        self.assertEqual(report.recovered, 1)
        self.assertEqual(len(report.files), 1)
        with self.assertRaisesRegex(ValueError, 'same_folders'):
            recover_folder(self.input, self.input)

    def test_malformed_candidate_and_missing_root(self):
        self.write('PM9_truncated', JPEG[:-5])
        report, path = recover_folder(self.input, self.output)
        self.assertEqual((report.recovered, report.skipped), (0, 1))
        self.assertEqual(report.files[0].rejected_candidates, 1)
        self.assertTrue(path.is_file())
        with self.assertRaisesRegex(ValueError, 'input_folder_missing'):
            recover_folder(self.root / 'missing', self.output)

    def test_atomic_publication_does_not_leave_partial_jpg(self):
        self.output.mkdir()
        with patch('kinect_photos.recovery.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                _publish(self.output, 'test', '.jpg', JPEG)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_partial_file_error_keeps_good_photos_and_report(self):
        self.write('PM9_good', JPEG)
        self.write('PM9_large', JPEG + b'extra')
        with patch('kinect_photos.jpeg.MAX_FILE_BYTES', len(JPEG)):
            report, path = recover_folder(self.input, self.output)
        self.assertEqual((report.recovered, report.failed), (1, 1))
        self.assertEqual(report.files[1].error, 'file_too_large')
        self.assertTrue(path.exists())

    def test_no_candidates_writes_truthful_report(self):
        self.write('unrelated', b'not a photo')
        report, path = recover_folder(self.input, self.output)
        self.assertEqual((report.inspected, len(report.files), report.recovered), (1, 0, 0))
        self.assertTrue(path.is_file())


if __name__ == '__main__':
    unittest.main()
