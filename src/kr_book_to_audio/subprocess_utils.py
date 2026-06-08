from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence, Any
import os
import subprocess
import threading
import time

TraceCallback = Callable[[dict[str, object]], None]
_TRACE = threading.local()


def _tool_name(args: Sequence[object] | str) -> str:
    if isinstance(args, str):
        first = args.strip().split(maxsplit=1)[0] if args.strip() else ''
    else:
        first = str(args[0]) if args else ''
    return Path(first).name or first or 'unknown'


def hidden_subprocess_kwargs(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return subprocess kwargs that suppress child console windows on Windows.

    The function is deliberately platform-neutral: non-Windows hosts receive the
    original kwargs unchanged so Linux CI exercises normal subprocess behavior.
    """
    kwargs: dict[str, Any] = dict(overrides or {})
    if os.name != 'nt':
        return kwargs
    flags = int(kwargs.get('creationflags', 0))
    flags |= int(getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
    kwargs['creationflags'] = flags
    startupinfo = kwargs.get('startupinfo')
    if startupinfo is None:
        startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= int(getattr(subprocess, 'STARTF_USESHOWWINDOW', 0x00000001))
    startupinfo.wShowWindow = int(getattr(subprocess, 'SW_HIDE', 0))
    kwargs['startupinfo'] = startupinfo
    return kwargs


def _emit(payload: dict[str, object]) -> None:
    callback = getattr(_TRACE, 'callback', None)
    if callback:
        try:
            callback(payload)
        except Exception:
            # Runtime tracing is diagnostic-only and must never break the pipeline.
            pass


@contextmanager
def process_trace(callback: TraceCallback | None, *, operation: str | None = None) -> Iterator[None]:
    """Attach an operation-scoped child-process trace callback for one worker."""
    previous_callback = getattr(_TRACE, 'callback', None)
    previous_operation = getattr(_TRACE, 'operation', None)
    _TRACE.callback = callback
    _TRACE.operation = operation
    try:
        yield
    finally:
        _TRACE.callback = previous_callback
        _TRACE.operation = previous_operation


def run_hidden_cli(args: Sequence[object] | str, **kwargs: Any) -> subprocess.CompletedProcess:
    """Run a console-style child process without flashing a Windows console."""
    tool = _tool_name(args)
    started = time.monotonic()
    _emit({'phase': 'start', 'tool': tool, 'operation': getattr(_TRACE, 'operation', None), 'visibility': 'hidden-window'})
    try:
        result = subprocess.run(args, **hidden_subprocess_kwargs(kwargs))
    except Exception as exc:
        _emit({'phase': 'error', 'tool': tool, 'operation': getattr(_TRACE, 'operation', None), 'visibility': 'hidden-window', 'error': f'{type(exc).__name__}: {exc}', 'elapsed_seconds': round(time.monotonic() - started, 3)})
        raise
    _emit({'phase': 'finish', 'tool': tool, 'operation': getattr(_TRACE, 'operation', None), 'visibility': 'hidden-window', 'returncode': int(result.returncode), 'elapsed_seconds': round(time.monotonic() - started, 3)})
    return result


def popen_hidden_cli(args: Sequence[object] | str, **kwargs: Any) -> subprocess.Popen:
    """Launch a console-style child process asynchronously without a visible console."""
    tool = _tool_name(args)
    _emit({'phase': 'start', 'tool': tool, 'operation': getattr(_TRACE, 'operation', None), 'visibility': 'hidden-window', 'async': True})
    return subprocess.Popen(args, **hidden_subprocess_kwargs(kwargs))
