import contextlib
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from kinect_photos.gui import launch
from kinect_photos.recovery import RecoveryReport


class FolderCliTests(unittest.TestCase):
    def test_discovery_failures_are_reported_even_when_photos_succeed(self):
        report = RecoveryReport(recovered=1, discovery_issue_count=1,
                                discovery_issues=('unreadable-folder',))
        output = io.StringIO()
        with patch('sys.argv', ['KinectPhotos', '--input-folder', 'input', '--output-folder', 'output']), \
             patch('kinect_photos.gui.recover_folder', return_value=(report, Path('report.json'))), \
             contextlib.redirect_stdout(output):
            self.assertEqual(launch(), 1)
        self.assertIn('Could not inspect 1 files or folders', output.getvalue())
