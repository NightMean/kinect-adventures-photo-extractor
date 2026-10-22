"""Gooey desktop interface: exactly two folders, with recursion always enabled."""

from importlib.metadata import version
from importlib import resources
import json
import os
from pathlib import Path
import subprocess
import sys

from .cli import TEXT
from .recovery import recover_folder


def configure_windows_transport() -> None:
    """Keep shell-free Gooey worker arguments valid for drive roots and spaces."""
    if os.name != 'nt':
        return
    from gooey.gui import formatters
    from gooey.gui.util import quoting
    from gooey.python_bindings import config_generator

    # Gooey 1.0.8.1 wraps paths in quotes without escaping trailing backslashes.
    # Replace its three quote bindings with the standard Windows argv encoder.
    def quote(value: str) -> str:
        return subprocess.list2cmdline([str(value)])

    quoting.quote = formatters.quote = config_generator.quote = quote


def build_label() -> str:
    release = version('kinect-adventures-photo-extractor')
    try:
        identity = json.loads(resources.files('kinect_photos').joinpath('build-info.json').read_text('utf-8'))
    except FileNotFoundError:
        return release
    suffix = '-dirty' if identity['dirty'] else ''
    return f"{release}+{identity['commit']}{suffix}"


def _run() -> int:
    from gooey import GooeyParser

    parser = GooeyParser(description=TEXT['gui_description'])
    parser.add_argument('--input-folder', required=True, type=Path,
                        metavar=TEXT['input_label'], help=TEXT['input_help'], widget='DirChooser')
    parser.add_argument('--output-folder', required=True, type=Path,
                        metavar=TEXT['output_label'], help=TEXT['output_help_gui'], widget='DirChooser')
    args = parser.parse_args()
    if args is None:
        return 0  # Gooey returns here after its configuration window closes.
    print(TEXT['discovering'], flush=True)
    try:
        report, report_path = recover_folder(args.input_folder, args.output_folder,
                                            version=build_label(),
                                            progress=lambda current, total: print(f'PROGRESS {current}/{total}', flush=True))
    except (ValueError, OSError) as exc:
        message = TEXT.get(str(exc), TEXT['folder_io_error'])
        print(TEXT['error'].format(detail=message), flush=True)
        return 1
    print(TEXT['folder_summary'].format(recovered=report.recovered, existing=report.existing,
                                       skipped=report.skipped, failed=report.failed), flush=True)
    print(TEXT['report_saved'].format(path=report_path), flush=True)
    if report.discovery_issue_count:
        print(TEXT['discovery_issues'].format(count=report.discovery_issue_count), flush=True)
    if not report.recovered and not report.existing:
        print(TEXT['no_discovered_photos'], flush=True)
        return 1
    return 1 if report.failed or report.discovery_issue_count else 0


def launch() -> int:
    configure_windows_transport()
    from gooey import Gooey

    if '--version' in sys.argv or '-V' in sys.argv:
        print(build_label())
        return 0
    if '--ignore-gooey' in sys.argv:
        sys.argv.remove('--ignore-gooey')
        return _run()
    if len(sys.argv) > 1:
        return _run()
    name = TEXT['gui_title'].format(version=build_label())
    # Gooey runs the worker with --ignore-gooey; the child must not open a second UI.
    return Gooey(program_name=name, default_size=(700, 520), required_cols=1,
                 optional_cols=1, show_sidebar=False, requires_shell=False,
                 progress_regex=r'^PROGRESS (\d+)/(\d+)$',
                 progress_expr='x[0] / x[1] * 100', hide_progress_msg=True,
                 show_success_modal=False, show_failure_modal=False,
                 show_restart_button=False)(_run)()
