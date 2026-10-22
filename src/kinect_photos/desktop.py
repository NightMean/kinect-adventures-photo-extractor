"""Desktop composition and event wiring for browsing, previewing, and export."""

from pathlib import Path
from importlib import resources

import wx

from .catalog import PhotoCatalog, scan_folder
from .cli import TEXT
from .dialogs import show_about, show_details, show_guide
from .identity import app_identity
from .jobs import BackgroundJobs, Progress
from .recovery import recover_selection
from .widgets import INK, MUTED, PhotoList, PhotoPreview


def _key(entry):
    return entry.source.relative, entry.number, entry.source.digest


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=TEXT['app_title'], size=(1120, 760))
        self.SetIcons(wx.IconBundle(str(resources.files('kinect_photos').joinpath('assets/app.ico')),
                                   wx.BITMAP_TYPE_ICO))
        self.SetMinSize((900, 620))
        self.catalog: PhotoCatalog | None = None
        self.jobs = BackgroundJobs()
        self.busy = False
        self.closing = False
        self.preview_token = 0
        self.preserved = None
        self.report_path = None
        self.last_details = ''
        menu = wx.Menu()
        guide_item = menu.Append(wx.ID_HELP, TEXT['export_guide'])
        about_item = menu.Append(wx.ID_ABOUT, TEXT['about_button'])
        self.Bind(wx.EVT_MENU, lambda event: show_guide(self), guide_item)
        self.Bind(wx.EVT_MENU, lambda event: show_about(self), about_item)
        bar = wx.MenuBar()
        bar.Append(menu, TEXT['help_menu'])
        self.SetMenuBar(bar)
        self._build()
        self.Bind(wx.EVT_CLOSE, self._close)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._poll, self.timer)
        self.timer.Start(75)
        self.Centre()

    def _build(self):
        panel = wx.Panel(self)
        panel.SetBackgroundColour('#f9fbf8')
        panel.SetForegroundColour(INK)
        panel.SetFont(wx.Font(wx.FontInfo(10)))
        layout = wx.BoxSizer(wx.VERTICAL)
        folders = wx.FlexGridSizer(2, 3, 10, 12)
        folders.AddGrowableCol(1)
        self.input_field = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.output_field = wx.TextCtrl(panel, style=wx.TE_READONLY)
        self.input_field.SetName(TEXT['input_label'])
        self.output_field.SetName(TEXT['output_label'])
        self.input_button = wx.Button(panel, label=TEXT['choose_input'])
        self.output_button = wx.Button(panel, label=TEXT['choose_output'])
        button_width = max(self.input_button.GetBestSize().width, self.output_button.GetBestSize().width)
        for button in (self.input_button, self.output_button):
            button.SetMinSize((button_width, -1))
        self.input_button.Bind(wx.EVT_BUTTON, self._choose_input)
        self.output_button.Bind(wx.EVT_BUTTON, self._choose_output)
        for label, control, button in [(TEXT['input_label'], self.input_field, self.input_button),
                                       (TEXT['output_label'], self.output_field, self.output_button)]:
            folders.Add(wx.StaticText(panel, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            folders.Add(control, 1, wx.EXPAND)
            folders.Add(button, 0, wx.EXPAND)
        layout.Add(folders, 0, wx.EXPAND | wx.BOTTOM, 22)
        columns = wx.BoxSizer(wx.HORIZONTAL)
        left = wx.BoxSizer(wx.VERTICAL)
        list_tools = wx.BoxSizer(wx.HORIZONTAL)
        self.counts = wx.StaticText(panel, label=TEXT['no_photos_yet'])
        self.counts.SetFont(panel.GetFont().Bold())
        list_tools.Add(self.counts, 1, wx.ALIGN_CENTER_VERTICAL)
        self.all_button = wx.Button(panel, label=TEXT['select_all'])
        self.none_button = wx.Button(panel, label=TEXT['deselect_all'])
        self.rescan_button = wx.Button(panel, label=TEXT['rescan'])
        self.all_button.Bind(wx.EVT_BUTTON, lambda event: self.photo_list.select_all(True))
        self.none_button.Bind(wx.EVT_BUTTON, lambda event: self.photo_list.select_all(False))
        self.rescan_button.Bind(wx.EVT_BUTTON, lambda event: self.load_folder(Path(self.input_field.Value)))
        for button in (self.all_button, self.none_button, self.rescan_button):
            list_tools.Add(button, 0, wx.LEFT, 5)
        left.Add(list_tools, 0, wx.EXPAND | wx.BOTTOM, 10)
        self.photo_list = PhotoList(panel, self._preview, self._selection_changed)
        left.Add(self.photo_list, 1, wx.EXPAND)
        hint = wx.StaticText(panel, label=TEXT['selection_hint'])
        hint.SetForegroundColour(MUTED)
        left.Add(hint, 0, wx.TOP, 8)
        columns.Add(left, 2, wx.EXPAND | wx.RIGHT, 22)
        right = wx.BoxSizer(wx.VERTICAL)
        preview_title = wx.StaticText(panel, label=TEXT['preview_title'])
        preview_title.SetFont(panel.GetFont().Bold())
        right.Add(preview_title, 0, wx.BOTTOM, 10)
        self.preview_panel = PhotoPreview(panel)
        right.Add(self.preview_panel, 1, wx.EXPAND)
        self.preview_name = wx.StaticText(panel, label='')
        right.Add(self.preview_name, 0, wx.TOP | wx.EXPAND, 9)
        columns.Add(right, 1, wx.EXPAND)
        layout.Add(columns, 1, wx.EXPAND)
        self.progress = wx.Gauge(panel, range=1000)
        layout.Add(self.progress, 0, wx.EXPAND | wx.TOP, 18)
        bottom = wx.BoxSizer(wx.HORIZONTAL)
        self.status = wx.StaticText(panel, label=TEXT['choose_to_scan'])
        bottom.Add(self.status, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        self.details_button = wx.Button(panel, label=TEXT['details_button'])
        self.cancel_button = wx.Button(panel, label=TEXT['stop_button'])
        self.export_button = wx.Button(panel, label=TEXT['export_selected'])
        self.export_button.SetFont(panel.GetFont().Bold())
        self.export_button.SetDefault()
        self.details_button.Bind(wx.EVT_BUTTON, self._details)
        self.cancel_button.Bind(wx.EVT_BUTTON, self._cancel)
        self.export_button.Bind(wx.EVT_BUTTON, lambda event: self.start_export())
        for control in (self.details_button, self.cancel_button, self.export_button):
            bottom.Add(control, 0, wx.LEFT, 8)
        layout.Add(bottom, 0, wx.EXPAND | wx.TOP, 12)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(layout, 1, wx.EXPAND | wx.ALL, 18)
        panel.SetSizer(outer)
        self._update_actions()

    def _choose_input(self, event):
        with wx.DirDialog(self, TEXT['choose_input'], defaultPath=self.input_field.Value,
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.load_folder(Path(dialog.GetPath()))

    def _choose_output(self, event):
        with wx.DirDialog(self, TEXT['choose_output'], defaultPath=self.output_field.Value) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.set_output(Path(dialog.GetPath()))

    def set_output(self, path: Path):
        previous = Path(self.output_field.Value).resolve() if self.output_field.Value else None
        output = path.resolve()
        self.output_field.ChangeValue(str(output))
        if self.catalog and (output.is_relative_to(self.catalog.root) or
                             (previous and previous.is_relative_to(self.catalog.root))):
            self.load_folder(self.catalog.root)
        self._update_actions()

    def load_folder(self, path: Path):
        if self.busy:
            return
        root = path.resolve()
        self.preserved = {_key(self.catalog.photos[i]) for i in self.photo_list.view.checked_indices} if self.catalog and self.catalog.root == root else None
        self.input_field.ChangeValue(str(root))
        self.catalog = None
        self.photo_list.set_photos(())
        self.preview_token = 0
        self.preview_panel.show_message(TEXT['preview_empty'])
        self.preview_name.SetLabel('')
        self.last_details = ''
        self.report_path = None
        self.status.SetLabel(TEXT['scan_start'])
        self._set_busy(True)
        output = Path(self.output_field.Value) if self.output_field.Value else None
        def scan():
            return scan_folder(root, output, cancelled=self.jobs.stop.is_set,
                               progress=lambda p: self.jobs.publish_progress(Progress(p.phase, p.current, p.total, p.photos)))
        self.jobs.start('scan', scan)

    def _selection_changed(self):
        if hasattr(self, 'photo_list'):
            count = len(self.photo_list.view.photos)
            self.counts.SetLabel(TEXT['photo_counts'].format(count=count, selected=len(self.photo_list.view.checked_indices)) if count else TEXT['no_photos_yet'])
            self._update_actions()

    def _set_busy(self, value):
        self.busy = value
        if value:
            self.jobs.stop.clear()
            self.progress.SetValue(0)
        self._update_actions()

    def _update_actions(self):
        if not hasattr(self, 'export_button'):
            return
        has_photos = bool(self.catalog and self.catalog.photos)
        for control in (self.input_button, self.output_button, self.input_field, self.output_field):
            control.Enable(not self.busy)
        self.photo_list.Enable(has_photos and not self.busy)
        self.all_button.Enable(has_photos and not self.busy)
        self.none_button.Enable(has_photos and not self.busy)
        self.rescan_button.Enable(bool(self.input_field.Value) and not self.busy)
        # Keep the idle action hoverable so missing prerequisites have a native tooltip.
        self.export_button.Enable(not self.busy)
        self.export_button.SetToolTip(self._export_requirement() or TEXT['export_tooltip'])
        self.cancel_button.Enable(self.busy and not self.jobs.stop.is_set())
        self.details_button.Enable(bool(self.last_details) and not self.busy)

    def _preview(self, index):
        if self.busy or self.catalog is None:
            return
        entry = self.catalog.photos[index]
        self.preview_panel.show_message(TEXT['preview_loading'])
        self.preview_name.SetLabel(entry.source.path.name)
        self.preview_name.Wrap(300)
        self.preview_token = self.jobs.request_preview(entry)
        self.Layout()

    def _export_requirement(self):
        if not self.output_field.Value:
            return TEXT['export_folder_required']
        if not self.catalog or not self.catalog.photos:
            return TEXT['photos_required']
        if not self.photo_list.view.checked_indices:
            return TEXT['no_selection']
        return ''

    def start_export(self):
        if self.busy:
            return
        requirement = self._export_requirement()
        if requirement:
            self.status.SetLabel(requirement)
            if not self.output_field.Value:
                self.output_button.SetFocus()
            return
        catalog = self.catalog
        selected = tuple(sorted(self.photo_list.view.checked_indices))
        output = Path(self.output_field.Value)
        if any(catalog.photos[i].source.path.is_relative_to(output.resolve()) for i in selected) and output.resolve().is_relative_to(catalog.root):
            self.load_folder(catalog.root)
            return
        self.status.SetLabel(TEXT['export_start'])
        self._set_busy(True)
        self.preview_token = 0
        def export():
            return recover_selection(catalog, selected, output, version=app_identity().version,
                                     cancelled=self.jobs.stop.is_set,
                                     progress=lambda n, total: self.jobs.publish_progress(Progress('export', n, total)))
        self.jobs.start('export', export)

    def _poll(self, event):
        progress, result, preview = self.jobs.poll()
        if progress and not self.closing:
            if progress.total:
                self.progress.SetValue(min(1000, progress.current * 1000 // progress.total))
            else:
                self.progress.Pulse()
            key = {'discover': 'scan_inspecting', 'validate': 'scan_validating', 'export': 'export_progress'}[progress.phase]
            self.status.SetLabel(TEXT[key].format(current=progress.current, total=progress.total, photos=progress.photos))
        if result:
            self._set_busy(False)
            if self.closing:
                self._destroy()
                return
            if result.cancelled:
                self.status.SetLabel(TEXT['scan_stopped'])
                self.progress.SetValue(0)
            elif result.error:
                self.last_details = TEXT.get(result.error, TEXT['unexpected_error']) + ('\n' + result.detail if result.detail else '')
                self.status.SetLabel(TEXT['operation_failed'])
                wx.MessageBox(self.last_details, TEXT['error_title'], wx.OK | wx.ICON_ERROR, self)
            elif result.kind == 'scan':
                self._scanned(result.value)
            else:
                report, self.report_path = result.value
                if not report.cancelled:
                    self.progress.SetValue(1000)
                key = 'export_stopped' if report.cancelled else 'export_complete'
                self.status.SetLabel(TEXT[key].format(recovered=report.recovered, existing=report.existing, failed=report.failed))
                self.last_details = TEXT['report_saved'].format(path=self.report_path)
                for record in report.files[:200]:
                    if record.error:
                        self.last_details += '\n' + record.source + ': ' + TEXT.get(record.error, TEXT['file_io_error'])
            self._update_actions()
        if preview and preview.token == self.preview_token and not self.closing:
            if preview.error:
                self.preview_panel.show_message(TEXT.get(preview.error, TEXT['preview_unavailable']))
                if preview.detail:
                    self.last_details = preview.detail
                    self._update_actions()
            else:
                self.preview_panel.show_pixels(preview.value)

    def _scanned(self, catalog):
        self.catalog = catalog
        checked = {i for i, entry in enumerate(catalog.photos) if _key(entry) in self.preserved} if self.preserved is not None else None
        self.photo_list.set_photos(catalog.photos, checked)
        self.progress.SetValue(1000)
        if catalog.issues or catalog.discovery_issue_count:
            self.last_details = '\n'.join(issue.source + ': ' + TEXT.get(issue.code, issue.code) for issue in catalog.issues[:200])
            if catalog.discovery_issue_count:
                self.last_details += '\n' + TEXT['discovery_issues'].format(count=catalog.discovery_issue_count) + '\n' + '\n'.join(catalog.discovery_issues)
            self.status.SetLabel(TEXT['scan_issues'].format(count=len(catalog.issues) + catalog.discovery_issue_count))
        else:
            self.status.SetLabel(TEXT['ready'] if catalog.photos else TEXT['empty_scan'])
        self._update_actions()
        if catalog.photos:
            self.photo_list.SetItemState(0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                                        wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)

    def _cancel(self, event):
        self.jobs.stop.set()
        self.cancel_button.Disable()
        self.status.SetLabel(TEXT['stopping'])

    def _details(self, event):
        show_details(self, self.last_details)

    def _close(self, event):
        if self.busy:
            self.closing = True
            self._cancel(None)
            event.Veto()
        else:
            self._destroy()

    def _destroy(self):
        self.timer.Stop()
        self.jobs.close()
        self.Destroy()
