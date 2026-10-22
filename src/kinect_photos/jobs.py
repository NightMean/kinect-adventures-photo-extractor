"""One worker, cooperative cancellation, and bounded latest-result mailboxes."""

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import Event, Lock
import traceback
from typing import Callable

from .catalog import PhotoEntry
from .preview import decode_preview
from .recovery import OperationCancelled


@dataclass(frozen=True)
class Progress:
    phase: str
    current: int
    total: int = 0
    photos: int = 0


@dataclass(frozen=True)
class Outcome:
    kind: str
    token: int
    value: object = None
    error: str | None = None
    detail: str = ''
    cancelled: bool = False


def _execute(kind: str, token: int, work: Callable[[], object]) -> Outcome:
    try:
        return Outcome(kind, token, value=work())
    except OperationCancelled:
        return Outcome(kind, token, cancelled=True)
    except (ValueError, OSError) as exc:
        return Outcome(kind, token, error=str(exc) if isinstance(exc, ValueError) else 'file_io_error')
    except Exception as exc:
        # Thread boundary: retain a bounded, path/argument-free trace for Details.
        frames = traceback.extract_tb(exc.__traceback__)[-6:]
        detail = type(exc).__name__ + '\n' + '\n'.join(f'{f.name}:{f.lineno}' for f in frames)
        return Outcome(kind, token, error='unexpected_error', detail=detail)


class BackgroundJobs:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='photo-recovery')
        self.stop = Event()
        self.lock = Lock()
        self.main: Future | None = None
        self.preview: Future | None = None
        self.progress: Progress | None = None
        self.result: Outcome | None = None
        self.preview_result: Outcome | None = None
        self.token = 0
        self.pending_preview = None
        self.preview_active = False

    def publish_progress(self, progress: Progress) -> None:
        with self.lock:
            self.progress = progress

    def start(self, kind: str, work: Callable[[], object]) -> None:
        if self.main is not None and not self.main.done():
            raise RuntimeError('operation_already_running')
        self.invalidate_preview()
        self.stop.clear()
        with self.lock:
            self.result = self.progress = None
        def completed(future):
            outcome = future.result()
            with self.lock:
                self.result = outcome
        self.main = self.executor.submit(_execute, kind, 0, work)
        self.main.add_done_callback(completed)

    def invalidate_preview(self) -> None:
        with self.lock:
            self.token += 1
            self.pending_preview = None
            self.preview_result = None
            if self.preview and self.preview.cancel():
                self.preview_active = False

    def request_preview(self, entry: PhotoEntry) -> int:
        with self.lock:
            self.token += 1
            token = self.token
            self.preview_result = None
            self.pending_preview = (token, entry)
            if not self.preview_active:
                self.preview_active = True
                self.preview = self.executor.submit(self._preview_loop)
            return token

    def _preview_loop(self):
        while True:
            with self.lock:
                pending = self.pending_preview
                self.pending_preview = None
                if pending is None:
                    self.preview_active = False
                    return
            token, entry = pending
            outcome = _execute('preview', token, lambda: decode_preview(entry))
            with self.lock:
                if token == self.token:
                    self.preview_result = outcome

    def poll(self) -> tuple[Progress | None, Outcome | None, Outcome | None]:
        with self.lock:
            values = self.progress, self.result, self.preview_result
            self.progress = self.result = self.preview_result = None
        return values

    def close(self) -> None:
        self.stop.set()
        self.invalidate_preview()
        self.executor.shutdown(wait=False, cancel_futures=True)
