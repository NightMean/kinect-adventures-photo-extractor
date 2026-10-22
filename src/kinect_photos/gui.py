"""Launch the custom wxPython browser, or a headless whole-folder recovery."""

import argparse
from pathlib import Path
import sys

from .cli import TEXT
from .identity import app_identity
from .recovery import recover_folder


def launch() -> int:
    identity = app_identity()
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(description=TEXT['folder_description'])
        parser.add_argument('-V', '--version', action='version', version=identity.version)
        parser.add_argument('--input-folder', required=True, type=Path)
        parser.add_argument('--output-folder', required=True, type=Path)
        args = parser.parse_args()
        try:
            report, path = recover_folder(args.input_folder, args.output_folder, version=identity.version)
        except (ValueError, OSError) as exc:
            print(TEXT.get(str(exc), TEXT['folder_io_error']), file=sys.stderr)
            return 1
        print(TEXT['folder_summary'].format(recovered=report.recovered, existing=report.existing,
                                           skipped=report.skipped, failed=report.failed))
        print(TEXT['report_saved'].format(path=path))
        if report.discovery_issue_count:
            print(TEXT['discovery_issues'].format(count=report.discovery_issue_count))
        if not report.recovered and not report.existing:
            print(TEXT['no_photos'])
        return 0 if report.recovered + report.existing and not report.failed and not report.discovery_issue_count else 1
    import wx
    from .desktop import MainFrame

    app = wx.App(False)
    app.SetAppName(TEXT['app_title'])
    frame = MainFrame()
    frame.Show()
    app.MainLoop()
    return 0
