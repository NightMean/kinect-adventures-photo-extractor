import importlib.util
import json
import os
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name == 'nt' and importlib.util.find_spec('gooey'), 'Windows GUI dependencies required')
class GuiTransportTests(unittest.TestCase):
    def test_folder_arguments_roundtrip_through_real_gooey_formatter(self):
        from gooey.gui import formatters
        from kinect_photos.gui import configure_windows_transport

        configure_windows_transport()

        values = ['D:\\', 'C:\\backup with spaces\\', 'C:\\fotky_ž\\a & b']
        prefix = subprocess.list2cmdline([sys.executable, '-c',
                                         'import json,sys; print(json.dumps(sys.argv[1:]))'])
        command = prefix + ' ' + ' '.join(formatters.general({}, value) for value in values)
        result = subprocess.run(command, shell=False, capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout), values)
