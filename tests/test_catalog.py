import base64
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest

from kinect_photos.catalog import PhotoSelection, photo_date, read_photo, scan_folder
from kinect_photos.recovery import OperationCancelled, recover_selection

JPEG = base64.b64decode(json.loads((Path(__file__).parent / 'fixtures.json').read_text())[0]['data'])


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.input = self.root / 'backup'
        self.output = self.root / 'out'
        self.input.mkdir()

    def write(self, name, data):
        path = self.input / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_catalog_validates_images_and_records_provenance(self):
        self.write('nested/PM9_0_2010_12_28_17_54_36_57', JPEG + JPEG)
        self.write('PM9_broken', JPEG[:-3])
        events = []
        catalog = scan_folder(self.input, progress=events.append)
        self.assertEqual((len(catalog.photos), catalog.skipped), (2, 1))
        self.assertEqual(catalog.photos[0].date, datetime(2010, 12, 28, 17, 54, 36, 57000))
        self.assertEqual(catalog.photos[0].date_source, 'filename')
        self.assertEqual(read_photo(catalog.photos[1]), JPEG)
        self.assertEqual(catalog.issues[0].code, 'rejected_jpeg')
        self.assertEqual(events[-1].photos, 2)

    def test_date_fallback_and_invalid_console_clock(self):
        date, origin = photo_date('PM9_0_2011_2_30_1_2_3_4', 0)
        self.assertEqual(origin, 'modified')
        self.assertEqual(date.timestamp(), 0)
        self.assertEqual(photo_date('renamed', float('nan')), (None, 'unknown'))
        self.assertEqual(photo_date('PM9_1_2005_11_22_12_27_7_606', 0)[1], 'filename')

    def test_selected_second_image_only(self):
        self.write('PM9_two', JPEG + JPEG)
        catalog = scan_folder(self.input)
        report, path = recover_selection(catalog, (1,), self.output)
        self.assertEqual(report.recovered, 1)
        self.assertEqual([p.name for p in self.output.glob('*.jpg')], ['PM9_two_image_2.jpg'])
        self.assertTrue(path.exists())
        self.assertEqual((self.output / 'PM9_two_image_2.jpg').read_bytes(), JPEG)
        again, _ = recover_selection(catalog, (1,), self.output)
        self.assertEqual((again.recovered, again.existing), (0, 1))

    def test_changed_source_is_rejected_before_preview_and_export(self):
        source = self.write('PM9_one', JPEG)
        catalog = scan_folder(self.input)
        source.write_bytes(JPEG + b'changed')
        with self.assertRaisesRegex(ValueError, 'source_changed'):
            read_photo(catalog.photos[0])
        report, _ = recover_selection(catalog, (0,), self.output)
        self.assertEqual((report.failed, report.recovered), (1, 0))
        self.assertFalse(list(self.output.glob('*.jpg')))

    def test_cancellation_preserves_completed_images_and_report(self):
        self.write('PM9_two', JPEG + JPEG)
        catalog = scan_folder(self.input)
        stop = [False]
        def progress(current, total):
            stop[0] = True
        report, path = recover_selection(catalog, (0, 1), self.output,
                                          cancelled=lambda: stop[0], progress=progress)
        self.assertEqual(report.recovered, 1)
        self.assertTrue(report.cancelled)
        self.assertEqual(len(list(self.output.glob('*.jpg'))), 1)
        self.assertTrue(json.loads(path.read_text())['cancelled'])

    def test_scan_cancellation_and_selection_boundary(self):
        self.write('PM9_one', JPEG)
        with self.assertRaises(OperationCancelled):
            scan_folder(self.input, cancelled=lambda: True)
        catalog = scan_folder(self.input)
        for selected in [(), (-1,), (1,), (True,), ('0',)]:
            with self.subTest(selected=selected), self.assertRaises(ValueError):
                recover_selection(catalog, selected, self.output)
        self.assertFalse(self.output.exists())


class SelectionTests(unittest.TestCase):
    def test_all_none_and_shift_ranges_in_both_directions(self):
        model = PhotoSelection(8)
        self.assertEqual(model.checked, set(range(8)))
        model.all(False)
        model.toggle(2, True)
        model.toggle(5, True, shift=True)
        self.assertEqual(model.checked, {2, 3, 4, 5})
        model.toggle(4, False)
        model.toggle(1, False, shift=True)
        self.assertEqual(model.checked, {5})
        model.all(True)
        self.assertEqual(model.checked, set(range(8)))
        self.assertIsNone(model.anchor)
