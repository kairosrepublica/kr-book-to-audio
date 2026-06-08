from __future__ import annotations
from contextlib import contextmanager
from typing import Callable, Iterator
import os

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _windows_set_execution_state(flags: int) -> int:
    import ctypes
    return int(ctypes.windll.kernel32.SetThreadExecutionState(flags))


@contextmanager
def keep_computer_awake(enabled: bool = True, *, setter: Callable[[int], int] | None = None) -> Iterator[None]:
    """Prevent automatic system sleep for the lifetime of one long operation.

    This does not block manual sleep, shutdown or lid-close policy.
    """
    if not enabled or os.name != 'nt':
        yield
        return
    setter = setter or _windows_set_execution_state
    result = setter(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if not result:
        raise RuntimeError('Windows refused to enable keep-awake mode.')
    try:
        yield
    finally:
        setter(ES_CONTINUOUS)
