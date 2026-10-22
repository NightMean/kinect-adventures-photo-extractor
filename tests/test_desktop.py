"""Windows GUI integration: real native widgets, event bindings, worker and files."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == 'nt' and importlib.util.find_spec('wx'), 'Windows GUI dependencies required')
class DesktopTests(unittest.TestCase):
    def test_browse_preview_checkboxes_and_selected_export(self):
        import wx
        from kinect_photos.desktop import MainFrame
        self.app = wx.App.Get() or wx.App(False)
        frame = MainFrame()
        messages = []
        def pump(condition):
            deadline = time.monotonic() + 12
            def check():
                if condition() or messages or time.monotonic() >= deadline:
                    self.app.ExitMainLoop()
                else:
                    wx.CallLater(10, check)
            wx.CallAfter(check)
            self.app.MainLoop()
            self.assertEqual(messages, [])
            self.assertTrue(condition(), 'GUI operation did not finish within 12 seconds')
        def click(button):
            event = wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId())
            button.GetEventHandler().ProcessEvent(event)
        fixture = json.loads((Path(__file__).parent / 'fixtures.json').read_text())[0]
        data = base64.b64decode(fixture['data'])
        try:
            with tempfile.TemporaryDirectory() as temporary, patch('wx.MessageBox', side_effect=lambda text, *a, **k: messages.append(text)):
                root = Path(temporary)
                source = root / 'input' / 'nested'
                source.mkdir(parents=True)
                (source / 'PM9_0_2010_12_28_17_54_36_57').write_bytes(data + data)
                (source / 'PM9_other').write_bytes(data)
                output = root / 'output'
                frame.set_output(output)
                frame.Show()
                frame.load_folder(root / 'input')
                pump(lambda: not frame.busy)
                self.assertEqual(len(frame.catalog.photos), 3)
                self.assertEqual(len(frame.photo_list.view.checked_indices), 3)
                pump(lambda: frame.preview_panel.bitmap is not None)
                self.assertEqual(frame.preview_name.Label, 'PM9_0_2010_12_28_17_54_36_57')
                self.assertFalse(hasattr(frame, 'preview_date'))
                self.assertFalse(hasattr(frame, 'preview_source'))
                self.assertEqual(frame.input_button.Size, frame.output_button.Size)
                self.assertTrue(frame.GetIcon().IsOk())
                click(frame.none_button)
                self.assertEqual(frame.photo_list.view.checked_indices, set())
                self.assertIn('Select at least one', frame.export_button.GetToolTipText())
                click(frame.all_button)
                self.assertEqual(frame.photo_list.view.checked_indices, {0, 1, 2})
                frame.photo_list.CheckItem(0, False)
                wx.Yield()
                self.assertEqual(frame.photo_list.view.checked_indices, {1, 2})
                frame.photo_list.apply_check(1, False)
                frame.photo_list.apply_check(2, False, shift=True)
                self.assertEqual(frame.photo_list.view.checked_indices, set())
                frame.photo_list.CheckItem(1, True)
                frame.photo_list.CheckItem(2, True)
                wx.Yield()
                self.assertEqual(frame.photo_list.view.checked_indices, {1, 2})
                frame.photo_list.SetItemState(0, wx.LIST_STATE_FOCUSED, wx.LIST_STATE_FOCUSED)
                key = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
                key.SetKeyCode(wx.WXK_SPACE)
                frame.photo_list.GetEventHandler().ProcessEvent(key)
                self.assertEqual(frame.photo_list.view.checked_indices, {0, 1, 2})
                frame.photo_list.GetEventHandler().ProcessEvent(key)
                self.assertEqual(frame.photo_list.view.checked_indices, {1, 2})
                for column in (0, 0, 1, 1):
                    sort = wx.ListEvent(wx.wxEVT_LIST_COL_CLICK, frame.photo_list.GetId())
                    sort.SetColumn(column)
                    frame.photo_list.GetEventHandler().ProcessEvent(sort)
                    self.assertEqual(frame.photo_list.view.checked_indices, {1, 2})
                self.assertFalse(frame.photo_list.view.ascending)
                self.assertEqual(frame.photo_list.view.rows[0], 2)
                click(frame.export_button)
                pump(lambda: not frame.busy)
                self.assertEqual(len(list(output.glob('*.jpg'))), 2)
                self.assertTrue((output / 'PM9_0_2010_12_28_17_54_36_57_image_2.jpg').exists())
                self.assertFalse((output / 'PM9_0_2010_12_28_17_54_36_57.jpg').exists())
                for photo in output.glob('*.jpg'):
                    self.assertEqual(photo.read_bytes(), data)
                self.assertEqual(frame.progress.Value, 1000)
                self.assertEqual(frame.Title, 'Kinect Adventures Photo Extractor')
                self.assertTrue(frame.report_path.exists())
                frame.output_field.ChangeValue('')
                frame._update_actions()
                self.assertTrue(frame.export_button.IsEnabled())
                self.assertIn('Choose an export folder', frame.export_button.GetToolTipText())
                click(frame.export_button)
                self.assertFalse(frame.busy)
                self.assertIn('Choose an export folder', frame.status.Label)
                from kinect_photos.dialogs import AboutDialog
                with AboutDialog(frame) as about:
                    about.Show()
                    wx.Yield()
                    labels = [child.Label for child in about.GetChildren() if isinstance(child, wx.StaticText)]
                    self.assertIn('Author: NightMean', labels)
                    self.assertFalse(any('Michal' in label or 'private' in label for label in labels))
                    for child in about.GetChildren():
                        if isinstance(child, wx.StaticText):
                            self.assertLessEqual(abs(child.Position.x + child.Size.width / 2 - about.ClientSize.width / 2), 2)
        finally:
            if frame.jobs.preview:
                frame.jobs.preview.result(timeout=5)
            frame.Close()
            wx.Yield()
