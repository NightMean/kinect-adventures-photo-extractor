"""Native photo checklist and a resize-aware preview surface."""

import wx

from .cli import TEXT
from .photo_view import PhotoColumn, PhotoView
from .preview import PreviewPixels

INK = '#24352b'
MUTED = '#627064'
SURFACE = '#f3f6f2'
ERROR_SURFACE = '#ffe1dd'


class PhotoList(wx.ListCtrl):
    def __init__(self, parent, on_preview, on_selection):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_VIRTUAL | wx.BORDER_SIMPLE)
        self.view = PhotoView(())
        self.on_preview = on_preview
        self.on_selection = on_selection
        self.InsertColumn(0, TEXT['photo_column'], width=330)
        self.InsertColumn(1, TEXT['date_column'], width=210)
        if not self.EnableCheckBoxes():
            raise RuntimeError('Native photo checkboxes are unavailable on this platform.')
        self.SetAlternateRowColour('#f3f6f2')
        self.SetName(TEXT['photo_list_name'])
        self.Bind(wx.EVT_LIST_ITEM_CHECKED, self._checked)
        self.Bind(wx.EVT_LIST_ITEM_UNCHECKED, self._checked)
        self.Bind(wx.EVT_LIST_ITEM_FOCUSED, self._focused)
        self.Bind(wx.EVT_KEY_DOWN, self._key)
        self.Bind(wx.EVT_LIST_COL_CLICK, self._sort)

    def OnGetItemText(self, item, column):
        if not 0 <= item < len(self.view.rows):
            return ''
        entry = self.view.photos[self.view.rows[item]]
        if column == 0:
            return entry.source.path.name + (TEXT['image_number'].format(number=entry.number) if entry.number > 1 else '')
        if entry.date is None:
            return TEXT['unknown_date']
        suffix = TEXT['modified_suffix'] if entry.date_source == 'modified' else ''
        return entry.date.strftime('%Y-%m-%d %H:%M:%S') + suffix

    def OnGetItemIsChecked(self, item):
        return item in self.view.selection.checked

    def set_photos(self, photos, checked=None):
        self.view = PhotoView(photos, checked)
        self.SetItemCount(len(photos))
        self.ShowSortIndicator(-1)
        self.Refresh()
        self.on_selection()

    def select_all(self, checked):
        self.view.selection.all(checked)
        self.Refresh()
        self.on_selection()

    def apply_check(self, index, checked, shift=False):
        affected = self.view.selection.toggle(index, checked, shift)
        self.RefreshItems(affected.start, affected.stop - 1)
        self.on_selection()

    def _checked(self, event):
        index = event.GetIndex()
        if 0 <= index < len(self.view.rows):
            self.apply_check(index, event.GetEventType() == wx.EVT_LIST_ITEM_CHECKED.typeId,
                             wx.GetKeyState(wx.WXK_SHIFT))

    def _focused(self, event):
        index = event.GetIndex()
        if 0 <= index < len(self.view.rows):
            self.on_preview(self.view.rows[index])

    def _sort(self, event):
        column = event.GetColumn()
        if column not in (PhotoColumn.NAME, PhotoColumn.DATE):
            return
        focused = self.GetFocusedItem()
        focused_index = self.view.rows[focused] if focused >= 0 else None
        self.Freeze()
        try:
            self.SetItemState(-1, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
            self.view.sort(PhotoColumn(column))
            self.ShowSortIndicator(column, self.view.ascending)
            self.Refresh()
            if focused_index is not None:
                row = self.view.rows.index(focused_index)
                self.SetItemState(row, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                                  wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
                self.EnsureVisible(row)
        finally:
            self.Thaw()
        self.on_selection()

    def _key(self, event):
        if event.GetKeyCode() == wx.WXK_SPACE:
            index = self.GetFocusedItem()
            if index >= 0:
                self.apply_check(index, index not in self.view.selection.checked, shift=event.ShiftDown())
        elif event.GetKeyCode() == ord('A') and event.ControlDown():
            self.select_all(True)
        else:
            event.Skip()


class PhotoPreview(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.bitmap = None
        self.message = TEXT['preview_empty']
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((240, 230))
        self.Bind(wx.EVT_PAINT, self._paint)
        self.Bind(wx.EVT_SIZE, lambda event: self.Refresh())

    def show_message(self, message):
        self.bitmap = None
        self.message = message
        self.Refresh()

    def show_pixels(self, pixels: PreviewPixels):
        self.bitmap = wx.Bitmap(wx.Image(pixels.width, pixels.height, pixels.rgb))
        self.message = ''
        self.Refresh()

    def _paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(SURFACE))
        dc.Clear()
        width, height = self.GetClientSize()
        if self.bitmap:
            context = wx.GraphicsContext.Create(dc)
            scale = min((width - 20) / self.bitmap.Width, (height - 20) / self.bitmap.Height, 1.0)
            if context and scale > 0:
                w, h = self.bitmap.Width * scale, self.bitmap.Height * scale
                context.DrawBitmap(self.bitmap, (width - w) / 2, (height - h) / 2, w, h)
        elif self.message:
            dc.SetTextForeground(wx.Colour(MUTED))
            dc.SetFont(self.GetFont())
            lines = []
            for paragraph in self.message.split('\n'):
                line = ''
                for word in paragraph.split():
                    proposed = (line + ' ' + word).strip()
                    if line and dc.GetTextExtent(proposed).width > max(40, width - 24):
                        lines.append(line)
                        line = word
                    else:
                        line = proposed
                lines.append(line)
            line_height = dc.GetCharHeight() + 4
            for index, line in enumerate(lines):
                size = dc.GetTextExtent(line)
                dc.DrawText(line, max(8, (width - size.width) // 2), max(8, (height - line_height * len(lines)) // 2) + index * line_height)
