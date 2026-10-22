from datetime import datetime, timezone
from pathlib import Path
import unittest

from kinect_photos.catalog import PhotoEntry, SourceSnapshot
from kinect_photos.jpeg import Photo
from kinect_photos.photo_view import PhotoColumn, PhotoView


def entry(name, date, number=1):
    return PhotoEntry(SourceSnapshot(Path(name), name, 'digest'), number,
                      Photo(0, 10, 1, 1), date, 'filename' if date else 'unknown')


class PhotoViewTests(unittest.TestCase):
    def test_name_and_date_sort_keep_checked_identity_and_range_anchor(self):
        photos = (entry('Z', datetime(2010, 1, 1)), entry('a', datetime(2011, 1, 1)),
                  entry('b', None), entry('a', datetime(2011, 1, 1), 2))
        view = PhotoView(photos)
        view.selection.all(False)
        view.selection.toggle(0, True)
        view.sort(PhotoColumn.NAME)
        self.assertEqual(view.rows, [1, 3, 2, 0])
        self.assertEqual(view.checked_indices, {0})
        self.assertEqual(view.selection.anchor, 3)
        view.selection.toggle(1, True, shift=True)
        self.assertEqual(view.checked_indices, {0, 2, 3})
        view.sort(PhotoColumn.NAME)
        self.assertEqual(view.rows, [0, 2, 3, 1])
        view.sort(PhotoColumn.DATE)
        self.assertEqual(view.rows, [0, 1, 3, 2])
        view.sort(PhotoColumn.DATE)
        self.assertEqual(view.rows, [3, 1, 0, 2])
        self.assertEqual(view.checked_indices, {0, 2, 3})

    def test_unknown_dates_stay_last_and_mixed_clock_sources_sort_as_displayed(self):
        view = PhotoView((entry('unknown', None), entry('local', datetime(2010, 2, 1)),
                          entry('modified', datetime(2010, 1, 1, tzinfo=timezone.utc))), {2})
        view.sort(PhotoColumn.DATE)
        self.assertEqual(view.rows, [2, 1, 0])
        view.sort(PhotoColumn.DATE)
        self.assertEqual(view.rows, [1, 2, 0])
        self.assertEqual(view.checked_indices, {2})
        self.assertIsNone(view.selection.anchor)
