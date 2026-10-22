"""Export guidance, public About information, and copyable recovery details."""

import wx
import wx.adv
from importlib import resources

from .cli import TEXT
from .identity import app_identity


def show_guide(parent):
    dialog = wx.Dialog(parent, title=TEXT['guide_title'], size=(650, 620), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    layout = wx.BoxSizer(wx.VERTICAL)
    body = '\n\n'.join(TEXT[key] for key in ['guide_step1', 'guide_step2', 'guide_step3', 'guide_step4', 'guide_legacy'])
    control = wx.TextCtrl(dialog, value=body, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.BORDER_NONE)
    control.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
    layout.Add(control, 1, wx.EXPAND | wx.ALL, 20)
    layout.Add(dialog.CreateButtonSizer(wx.OK), 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
    dialog.SetSizer(layout)
    dialog.ShowModal()
    dialog.Destroy()


class AboutDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title=TEXT['about_title'])
        identity = app_identity()
        layout = wx.BoxSizer(wx.VERTICAL)
        icon = wx.Icon(str(resources.files('kinect_photos').joinpath('assets/app.ico')), wx.BITMAP_TYPE_ICO, 64, 64)
        self.SetIcon(icon)
        bitmap = wx.Bitmap()
        bitmap.CopyFromIcon(icon)
        layout.Add(wx.StaticBitmap(self, bitmap=bitmap), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 10)
        for key, values in [('about_name', {}), ('about_version', {'version': identity.version}),
                            ('about_author', {'author': identity.author})]:
            label = wx.StaticText(self, label=TEXT[key].format(**values), style=wx.ALIGN_CENTER)
            if key == 'about_name':
                label.SetFont(label.GetFont().Bold())
            layout.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        link = wx.adv.HyperlinkCtrl(self, label=TEXT['github_link'], url=identity.repository)
        layout.Add(link, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, 14)
        layout.Add(wx.StaticText(self, label=TEXT['about_license']), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 14)
        layout.Add(self.CreateButtonSizer(wx.OK), 0, wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM, 24)
        self.SetSizerAndFit(layout)
        self.CentreOnParent()


def show_about(parent):
    with AboutDialog(parent) as dialog:
        dialog.ShowModal()


def show_details(parent, text):
    dialog = wx.Dialog(parent, title=TEXT['details_title'], size=(650, 460), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    layout = wx.BoxSizer(wx.VERTICAL)
    layout.Add(wx.TextCtrl(dialog, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY), 1, wx.EXPAND | wx.ALL, 16)
    layout.Add(dialog.CreateButtonSizer(wx.OK), 0, wx.ALIGN_RIGHT | wx.ALL, 12)
    dialog.SetSizer(layout)
    dialog.ShowModal()
    dialog.Destroy()
