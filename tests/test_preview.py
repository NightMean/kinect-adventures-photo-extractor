import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from kinect_photos.catalog import scan_folder
from kinect_photos.preview import decode_preview


@unittest.skipUnless(importlib.util.find_spec('PIL'), 'Preview dependencies required')
class PreviewTests(unittest.TestCase):
    def test_real_jpeg_preview_leaves_source_unchanged(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures.json').read_text())[0]
        data = base64.b64decode(fixture['data'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'PM9_demo'
            source.write_bytes(data)
            entry = scan_folder(root).photos[0]
            pixels = decode_preview(entry)
            self.assertEqual((pixels.width, pixels.height, len(pixels.rgb)), (24, 16, 24 * 16 * 3))
            self.assertEqual(source.read_bytes(), data)
