from threading import Event
import unittest
from unittest.mock import patch

from kinect_photos.jobs import BackgroundJobs, Progress
from kinect_photos.recovery import OperationCancelled


class BackgroundTests(unittest.TestCase):
    def setUp(self):
        self.jobs = BackgroundJobs()
        self.addCleanup(self.jobs.close)

    def test_main_result_is_delivered_after_future_completion(self):
        self.jobs.start('scan', lambda: 42)
        self.jobs.main.result(timeout=3)
        _, result, _ = self.jobs.poll()
        self.assertEqual(result.value, 42)
        self.assertTrue(self.jobs.main.done())
        self.jobs.start('export', lambda: 7)
        self.jobs.main.result(timeout=3)
        self.assertEqual(self.jobs.poll()[1].value, 7)

    def test_progress_is_coalesced_and_cancellation_is_explicit(self):
        for index in range(10000):
            self.jobs.publish_progress(Progress('discover', index))
        self.assertEqual(self.jobs.poll()[0].current, 9999)
        self.assertIsNone(self.jobs.poll()[0])
        def cancel():
            raise OperationCancelled()
        self.jobs.start('scan', cancel)
        self.jobs.main.result(timeout=3)
        self.assertTrue(self.jobs.poll()[1].cancelled)

    def test_preview_queue_keeps_only_the_latest_pending_request(self):
        started, release = Event(), Event()
        decoded = []
        def decode(entry):
            decoded.append(entry)
            if entry == 'first':
                started.set()
                self.assertTrue(release.wait(3))
            return entry
        with patch('kinect_photos.jobs.decode_preview', decode):
            self.jobs.request_preview('first')
            self.assertTrue(started.wait(3))
            for index in range(100):
                token = self.jobs.request_preview(index)
            release.set()
            self.jobs.preview.result(timeout=3)
            result = self.jobs.poll()[2]
        self.assertEqual(decoded, ['first', 99])
        self.assertEqual((result.token, result.value), (token, 99))
